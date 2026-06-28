"""
Señales de hoy — pipeline de producción con Ensemble v1 + HMM régimen.

Flujo:
  1. Actualiza store local de datos
  2. Calcula features (25 técnicas + 4 macro)
  3. Entrena EnsembleModel (WoE + LR + LightGBM) en últimos 3 años
  4. Detecta régimen de mercado con HMM (bull/lateral/bear)
  5. Genera P(subida 5d) para el estado de HOY de cada ticker
  6. Aplica Risk Engine: Kelly, ATR stops, correlación
  7. Guarda JSON con señales + régimen HMM para el dashboard

Ejecución:
    python scripts/generate_signals.py [--capital 10000]
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.ml.features    import compute_features, add_macro_features, FEATURE_COLS, add_cross_section_features, CROSS_SECTION_COLS
from src.ml.woe         import compute_all_woe, woe_transform
from src.ml.ensemble    import EnsembleModel
from src.ml.pipeline    import train_pipeline, ProductionModel, market_is_riskon
from src.ml.regime      import RegimeDetector
from src.ml.risk_engine import (
    build_signal, portfolio_summary,
    compute_correlation_matrix, correlation_penalty,
)
from src.data.store import get as store_get, update_all as store_update, BMV_TICKERS, MACRO_TICKERS

TRAIN_YEARS  = 3       # años de datos para entrenar
WARMUP       = 60      # días mínimos de warmup
HORIZON      = 5
PROB_THRESH  = 0.53
MAX_SIGNALS  = 5
MAX_POSITION = 0.10
KELLY_FRAC   = 0.25


# ─── 1. Carga de datos ────────────────────────────────────────────────────────

def load_data() -> tuple[dict, dict]:
    print("Actualizando store local...")
    store_update(verbose=True)

    macro: dict[str, pd.DataFrame] = {}
    for name in MACRO_TICKERS:
        df = store_get(name)
        if df is not None:
            macro[name] = df

    data: dict[str, pd.DataFrame] = {}
    print("\nCargando tickers...\n")
    for ticker in BMV_TICKERS:
        raw = store_get(ticker)
        if raw is not None and len(raw) >= WARMUP + HORIZON + 30:
            data[ticker] = raw
            print(f"  {ticker:<12} {len(raw)} días  |  último: {raw.index[-1].date()}")
    return data, macro


# ─── 2. Entrena EnsembleModel ────────────────────────────────────────────────

def train_ensemble(
    data:  dict[str, pd.DataFrame],
    macro: dict[str, pd.DataFrame],
) -> tuple[ProductionModel, dict, list]:
    """
    Construye dataset de entrenamiento con los últimos TRAIN_YEARS y entrena
    el pipeline completo (Ensemble + Meta-labeling) con features cross-seccionales.

    Returns: (model, feat_frames, all_feature_cols)
    """
    cutoff = pd.Timestamp.today() - pd.DateOffset(years=TRAIN_YEARS)

    # 1. Features individuales
    feat_frames: dict[str, pd.DataFrame] = {}
    for ticker, raw in data.items():
        try:
            df = compute_features(raw)
            df = add_macro_features(df, macro)
            df["y"]       = (raw["Close"].shift(-HORIZON) / raw["Close"] - 1 > 0).astype(int)
            df["ret_fwd"] = (raw["Close"].shift(-HORIZON) / raw["Close"] - 1) * 100
            df["ticker"]  = ticker
            df = df.loc[cutoff:]
            feat_frames[ticker] = df
        except Exception as e:
            print(f"  {ticker}: error features — {e}")

    # 2. Features cross-seccionales
    feat_frames = add_cross_section_features(feat_frames)

    all_feature_cols = FEATURE_COLS  # ya incluye CROSS_SECTION_COLS

    rows = []
    for name, feat in feat_frames.items():
        available = [c for c in all_feature_cols if c in feat.columns]
        feat_clean = feat.dropna(subset=available + ["y"])
        if len(feat_clean) > 30:
            rows.append(feat_clean)

    if not rows:
        raise RuntimeError("Sin datos para entrenamiento")

    n_obs = sum(len(r) for r in rows)
    print(f"\nEntrenando pipeline (Ensemble + Meta-labeling) sobre {n_obs:,} obs "
          f"({len(feat_frames)} tickers, "
          f"{len(FEATURE_COLS)} features)...")

    model = train_pipeline(
        feat_frames, data, feature_cols=all_feature_cols,
        target_col="y", primary_thresh=PROB_THRESH, use_meta=True,
    )
    print(model.primary.summary())
    if model.meta is not None:
        print(f"  Meta AUC={model.meta.auc:.4f}  cut={model.meta_cut:.3f}  "
              f"precisión={model.meta.precision:.3f}")
    return model, feat_frames, all_feature_cols


# ─── 3. Detecta régimen HMM ──────────────────────────────────────────────────

def detect_regime(macro: dict) -> dict:
    """
    Detecta el régimen actual del mercado con HMM sobre NAFTRAC.
    Devuelve dict con 'state', 'proba', 'is_favorable'.
    """
    naftrac = macro.get("NAFTRAC")
    sp500   = macro.get("SP500")

    if naftrac is None:
        return {"state": "unknown", "proba": {}, "is_favorable": True}

    try:
        detector = RegimeDetector(n_states=3, n_iter=200)
        detector.fit(naftrac, sp500)
        state   = detector.predict_current(naftrac, sp500)
        proba   = detector.state_proba(naftrac, sp500)
        favor   = detector.is_favorable(naftrac, sp500)
        stats   = detector.regime_stats(naftrac, sp500).to_dict("records")
        return {
            "state":        state,
            "proba":        {k: round(v, 3) for k, v in proba.items()},
            "is_favorable": favor,
            "stats":        stats,
        }
    except Exception as e:
        print(f"  HMM error: {e}")
        return {"state": "unknown", "proba": {}, "is_favorable": True}


# ─── 4. Predicciones para HOY ────────────────────────────────────────────────

def predict_today(
    data:         dict[str, pd.DataFrame],
    macro:        dict[str, pd.DataFrame],
    model:        ProductionModel,
    feat_frames:  dict[str, pd.DataFrame],
    all_feature_cols: list[str],
) -> list[dict]:
    """Genera predicciones para HOY usando el pipeline (Ensemble + Meta)."""
    predictions = []

    for ticker, feat in feat_frames.items():
        try:
            feat_clean = feat.dropna(subset=[c for c in all_feature_cols if c in feat.columns])
            if len(feat_clean) == 0:
                continue

            last = feat_clean.iloc[[-1]]
            pred = model.predict_one(last)

            raw    = data[ticker]
            price  = float(raw["Close"].iloc[-1])
            atr14  = float(last["_atr14"].iloc[0]) if "_atr14" in last.columns \
                     else price * 0.02

            predictions.append({
                "ticker":  ticker,
                "price":   round(price, 2),
                "atr14":   round(atr14, 4),
                "p_up":    round(pred["p_primary"], 4),
                "p_meta":  round(pred["p_meta"], 4) if pred["p_meta"] is not None else None,
                "take":    pred["take"],
                "date":    str(raw.index[-1].date()),
                "features": {
                    f: round(float(last[f].iloc[0]), 4)
                    for f in model.primary.top_feats if f in last.columns
                },
            })
        except Exception as e:
            print(f"  {ticker}: error predicción — {e}")

    return sorted(predictions, key=lambda x: x["p_up"], reverse=True)


# ─── 5. Risk Engine ───────────────────────────────────────────────────────────

def apply_risk_engine(
    predictions: list[dict],
    capital:     float,
    data:        dict[str, pd.DataFrame],
    regime:      dict,
    macro:       dict[str, pd.DataFrame] | None = None,
) -> tuple[list, dict, list]:
    """
    Filtra por umbral (ajustado por régimen), calcula Kelly, stops, correlación.
    En régimen BEAR sube el umbral a 0.56 — requiere más confianza.
    """
    # Ajuste de umbral por régimen
    thresh = PROB_THRESH
    if regime.get("state") == "bear":
        thresh = 0.56
        print(f"  ⚠️  Régimen BEAR — umbral subido a {thresh}")
    elif regime.get("state") == "bull":
        thresh = 0.52
        print(f"  ✅  Régimen BULL — umbral bajado a {thresh}")

    returns_dict = {
        t: data[t]["Close"].pct_change()
        for t in data
        if "Close" in data[t].columns
    }
    corr_matrix = compute_correlation_matrix(returns_dict, window=63)

    # Filtro de régimen de mercado: si NAFTRAC está bajo su MA20, no operar
    naftrac = macro.get("NAFTRAC") if macro else None
    market_riskon = market_is_riskon(naftrac)
    if not market_riskon:
        print("  🔴 Mercado RISK-OFF (NAFTRAC bajo su MA20) — sin señales hoy")
        return [], portfolio_summary([], capital), [
            {"ticker": p["ticker"], "price": p["price"], "p_up": p["p_up"],
             "p_meta": p.get("p_meta"), "take": p.get("take"),
             "date": p["date"], "features": p["features"]}
            for p in predictions
        ], corr_matrix

    # Candidatos sobre el umbral, rankeados por confianza del meta-modelo
    primary_candidates = [p for p in predictions if p["p_up"] >= thresh]
    has_meta = any(p.get("p_meta") is not None for p in primary_candidates)
    if has_meta:
        candidates = sorted(
            primary_candidates,
            key=lambda p: (p.get("take", False), p.get("p_meta") or 0, p["p_up"]),
            reverse=True,
        )
        n_take = sum(1 for p in primary_candidates if p.get("take"))
        print(f"  Meta-labeling: {n_take} de {len(primary_candidates)} candidatos aprobados")
    else:
        candidates = primary_candidates

    signals, selected = [], []

    for p in candidates:
        if len(signals) >= MAX_SIGNALS:
            break

        corr_f = correlation_penalty(p["ticker"], corr_matrix, selected)
        signal = build_signal(
            ticker       = p["ticker"],
            price        = p["price"],
            atr          = p["atr14"],
            p_up         = p["p_up"],
            capital_mxn  = capital,
            corr_factor  = corr_f,
            features     = p["features"],
            kelly_frac   = KELLY_FRAC,
            max_position = MAX_POSITION,
        )
        if signal is None:
            continue
        signals.append(signal)
        selected.append(p["ticker"])

    summary = portfolio_summary(signals, capital)
    all_candidates = [
        {"ticker": p["ticker"], "price": p["price"],
         "p_up": p["p_up"], "p_meta": p.get("p_meta"), "take": p.get("take"),
         "date": p["date"], "features": p["features"]}
        for p in predictions
    ]
    return signals, summary, all_candidates, corr_matrix


# ─── 6. Output ────────────────────────────────────────────────────────────────

def print_signals(signals, summary, capital, regime):
    icon_map = {"bull": "✅", "lateral": "⚡", "bear": "⚠️", "unknown": "❓"}
    icon = icon_map.get(regime.get("state", "unknown"), "❓")

    print(f"\n{'='*66}")
    print(f"  SEÑALES — {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  ${capital:,.0f} MXN")
    print(f"  Régimen: {icon} {regime.get('state','?').upper()}  "
          f"P(bull)={regime.get('proba',{}).get('bull',0):.0%}  "
          f"P(bear)={regime.get('proba',{}).get('bear',0):.0%}")
    print(f"{'='*66}\n")

    if not signals:
        print(f"  Sin señales hoy (P > umbral ajustado por régimen).\n")
        return

    for i, s in enumerate(signals, 1):
        rr = f"{s.rr_ratio:.1f}R" if s.rr_ratio else "—"
        print(f"  #{i} {s.ticker:<12} P={s.p_up:.1%}  Entry={s.entry:.2f}  "
              f"Stop={s.stop:.2f}  T1={s.target_1:.2f}  T2={s.target_2:.2f}")
        print(f"      {s.pct_capital:.1f}% cap  ${s.capital_mxn:,.0f} MXN  "
              f"{s.shares} acc  R/R={rr}")
        print()

    print(f"  Portfolio: {summary['n_positions']} pos  "
          f"{summary['pct_invested']:.1f}% inv  {summary['pct_at_risk']:.2f}% riesgo\n")


def fetch_market_context() -> dict:
    """Trae contexto de mercado en vivo (tasas, índices, noticias) + sentimiento LLM."""
    try:
        from src.utils.config import Config
        from src.api.market_context import market_context, score_news_sentiment
        token = Config.DATABURSATIL_API_TOKEN
        if not token:
            return {}
        ctx = market_context(token)
        sent = score_news_sentiment(ctx.get("news", []))
        if sent:
            ctx["sentiment"] = sent
        return ctx
    except Exception as e:
        print(f"  ⚠️  Contexto de mercado no disponible: {e}")
        return {}


def save_output(signals, summary, all_candidates, corr_matrix, capital, regime,
                context: dict | None = None) -> Path:
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    sigs_out = []
    for s in signals:
        sigs_out.append({
            "ticker":      s.ticker,
            "price":       s.price,
            "atr":         s.atr,
            "p_up":        s.p_up,
            "entry":       s.entry,
            "stop":        s.stop,
            "target_1":    s.target_1,
            "target_2":    s.target_2,
            "kelly_f":     s.kelly_f,
            "pct_capital": s.pct_capital,
            "shares":      s.shares,
            "capital_mxn": s.capital_mxn,
            "risk_pct":    s.risk_pct,
            "rr_ratio":    s.rr_ratio,
            "edge":        s.edge,
            "features":    s.features,
            "reason":      s.reason,
        })

    tickers_in = [s.ticker for s in signals]
    corr_top   = {}
    for t in tickers_in:
        if t in corr_matrix.index:
            row = corr_matrix.loc[t].drop(labels=[t], errors="ignore")
            corr_top[t] = {k: round(float(v), 3) for k, v in row.items()}

    out = {
        "meta": {
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "capital":   capital,
            "threshold": PROB_THRESH,
            "horizon":   HORIZON,
            "model":     "EnsembleV1 (WoE+LR+LightGBM)",
        },
        "regime":        regime,
        "signals":       sigs_out,
        "summary":       summary,
        "all_candidates": all_candidates[:19],
        "correlations":  corr_top,
        "market_context": context or {},
    }

    path = data_dir / "signals_today.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"  Guardado: {path}\n")
    return path


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=10_000)
    args = parser.parse_args()

    print("\n" + "=" * 66)
    print("  BMV Trading — Ensemble v1 (WoE + LR + LightGBM) + HMM")
    print("=" * 66 + "\n")

    data, macro = load_data()

    print("\nDetectando régimen de mercado (HMM)...")
    regime = detect_regime(macro)
    regime["market_riskon"] = market_is_riskon(macro.get("NAFTRAC"))
    state  = regime.get("state", "unknown")
    proba  = regime.get("proba", {})
    mkt    = "🟢 RISK-ON" if regime["market_riskon"] else "🔴 RISK-OFF"
    print(f"  Régimen actual: {state.upper()}  "
          f"bull={proba.get('bull',0):.0%}  "
          f"lateral={proba.get('lateral',0):.0%}  "
          f"bear={proba.get('bear',0):.0%}  |  {mkt}")

    print("\nEntrenando EnsembleModel...")
    model, feat_frames, all_feature_cols = train_ensemble(data, macro)

    print("\nGenerando predicciones para HOY...")
    preds = predict_today(data, macro, model, feat_frames, all_feature_cols)

    print("\nAplicando risk engine...")
    signals, summary, all_candidates, corr_matrix = apply_risk_engine(
        preds, args.capital, data, regime, macro
    )

    print("\nTrayendo contexto de mercado en vivo (tasas, índices, noticias)...")
    context = fetch_market_context()
    if context:
        r = context.get("rates", {})
        tobj = r.get("Tasa_Objetivo", {}).get("tasa")
        ipc = context.get("indices", {}).get("IPC", {})
        print(f"  Tasa objetivo: {tobj}%  |  IPC: {ipc.get('nivel')} ({ipc.get('cambio_pct')}%)  "
              f"|  Noticias: {context.get('n_news', 0)}")
        if context.get("sentiment"):
            s = context["sentiment"]
            print(f"  Sentimiento LLM: {s.get('score'):+.2f} ({s.get('etiqueta')})")

    print_signals(signals, summary, args.capital, regime)
    save_output(signals, summary, all_candidates, corr_matrix, args.capital, regime, context)


if __name__ == "__main__":
    main()
