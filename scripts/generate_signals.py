"""
Señales BMV de hoy — pipeline unificado SuperModel + Gemini + Risk Engine.

Flujo:
  1. Actualiza store local
  2. SuperModel: 4 modelos (xs_lgbm, ensemble, heuristic, lstm) → stacking → convicción
  3. Gemini validator: CONFIRMA/DEGRADA/VETA + titulares por ticker BMV
  4. bet_policy: K=2, min convicción 0.56, paper only
  5. Risk engine: Kelly, ATR stops, correlación
  6. Guarda data/signals_today.json + data/super_signals.json

Legacy (--legacy): Ensemble v1 + meta-labeling sin SuperModel/Gemini.

Ejecución:
    python scripts/generate_signals.py [--capital 10000]
    python scripts/generate_signals.py --no-gemini          # solo cuantitativo
    python scripts/generate_signals.py --legacy             # Ensemble v1 antiguo
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.data.store import get as store_get, update_all as store_update, BMV_TICKERS, MACRO_TICKERS
from src.ml.features import compute_features, add_macro_features, FEATURE_COLS, add_cross_section_features
from src.ml.pipeline import train_pipeline, market_is_riskon
from src.ml.risk_engine import build_signal, portfolio_summary, compute_correlation_matrix, correlation_penalty
from src.ml.bet_policy import (
    KELLY_FRAC, MAX_POSITION_PCT, MAX_SIGNALS, PROB_THRESH_BASE, prob_thresh_for_regime,
)
from src.ml.signal_pipeline import (
    detect_regime_hmm,
    generate_bmv_signals,
    signal_to_dict,
)

WARMUP = 60
HORIZON = 5
TRAIN_YEARS = 3


def load_data() -> tuple[dict, dict]:
    print("Actualizando store local...")
    store_update(verbose=True)

    macro: dict[str, pd.DataFrame] = {}
    for name in MACRO_TICKERS:
        df = store_get(name)
        if df is not None:
            macro[name] = df

    data: dict[str, pd.DataFrame] = {}
    print("\nCargando tickers BMV...\n")
    for ticker in BMV_TICKERS:
        raw = store_get(ticker)
        if raw is not None and len(raw) >= WARMUP + HORIZON + 30:
            data[ticker] = raw
            print(f"  {ticker:<12} {len(raw)} días  |  último: {raw.index[-1].date()}")
    return data, macro


def fetch_market_context() -> dict:
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
        print("  Sin señales hoy (risk-off, umbral o veto Gemini).\n")
        return
    for i, s in enumerate(signals, 1):
        g = s.get("gemini", {}) if isinstance(s, dict) else {}
        ver = g.get("veredicto", "—") if g else "—"
        if isinstance(s, dict):
            print(f"  #{i} {s['ticker']:<12} conv={s['p_up']:.1%}  Gemini={ver}  "
                  f"Entry={s['entry']:.2f}  Stop={s['stop']:.2f}")
        else:
            rr = f"{s.rr_ratio:.1f}R" if s.rr_ratio else "—"
            print(f"  #{i} {s.ticker:<12} P={s.p_up:.1%}  Entry={s.entry:.2f}  "
                  f"Stop={s.stop:.2f}  R/R={rr}")
    print(f"\n  Portfolio: {summary['n_positions']} pos  "
          f"{summary['pct_invested']:.1f}% inv  {summary['pct_at_risk']:.2f}% riesgo\n")


def run_legacy(data, macro, capital) -> Path:
    """Pipeline Ensemble v1 (sin SuperModel/Gemini)."""
    cutoff = pd.Timestamp.today() - pd.DateOffset(years=TRAIN_YEARS)
    feat_frames: dict[str, pd.DataFrame] = {}
    for ticker, raw in data.items():
        try:
            df = compute_features(raw)
            df = add_macro_features(df, macro)
            df["y"] = (raw["Close"].shift(-HORIZON) / raw["Close"] - 1 > 0).astype(int)
            df["ticker"] = ticker
            feat_frames[ticker] = df.loc[cutoff:]
        except Exception as e:
            print(f"  {ticker}: error — {e}")

    feat_frames = add_cross_section_features(feat_frames)
    model = train_pipeline(
        feat_frames, data, feature_cols=FEATURE_COLS,
        target_col="y", primary_thresh=PROB_THRESH_BASE, use_meta=True,
    )

    regime = detect_regime_hmm(macro)
    regime["market_riskon"] = market_is_riskon(macro.get("NAFTRAC"))
    thresh = prob_thresh_for_regime(regime.get("state"))

    preds = []
    for ticker, feat in feat_frames.items():
        clean = feat.dropna(subset=[c for c in FEATURE_COLS if c in feat.columns])
        if clean.empty:
            continue
        last = clean.iloc[[-1]]
        pred = model.predict_one(last)
        raw = data[ticker]
        price = float(raw["Close"].iloc[-1])
        atr14 = float(last["_atr14"].iloc[-1]) if "_atr14" in last.columns else price * 0.02
        preds.append({
            "ticker": ticker, "price": price, "atr14": atr14,
            "p_up": pred["p_primary"], "take": pred["take"],
            "features": {f: float(last[f].iloc[0]) for f in model.primary.top_feats if f in last.columns},
        })

    returns_dict = {t: data[t]["Close"].pct_change() for t in data}
    corr_matrix = compute_correlation_matrix(returns_dict, window=63)
    signals, selected = [], []
    if regime["market_riskon"]:
        for p in sorted([x for x in preds if x["p_up"] >= thresh], key=lambda x: -x["p_up"]):
            if len(signals) >= MAX_SIGNALS:
                break
            cf = correlation_penalty(p["ticker"], corr_matrix, selected)
            sig = build_signal(
                ticker=p["ticker"], price=p["price"], atr=p["atr14"], p_up=p["p_up"],
                capital_mxn=capital, corr_factor=cf, features=p["features"],
                kelly_frac=KELLY_FRAC, max_position=MAX_POSITION_PCT,
            )
            if sig:
                signals.append(sig)
                selected.append(p["ticker"])

    summary = portfolio_summary(signals, capital)
    out = {
        "meta": {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "capital": capital, "threshold": thresh, "paper_only": True,
            "model": "EnsembleV1 (legacy)", "horizon": HORIZON,
        },
        "regime": regime,
        "signals": [signal_to_dict(s) for s in signals],
        "summary": summary,
        "all_candidates": [{"ticker": p["ticker"], "p_up": p["p_up"]} for p in preds[:19]],
        "correlations": {},
        "market_context": {},
    }
    path = ROOT / "data" / "signals_today.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print_signals(out["signals"], summary, capital, regime)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=10_000)
    parser.add_argument("--no-gemini", action="store_true", help="Saltar validación Gemini")
    parser.add_argument("--legacy", action="store_true", help="Ensemble v1 sin SuperModel")
    parser.add_argument("--no-stacking", action="store_true", help="Desactivar stacking LR")
    args = parser.parse_args()

    print("\n" + "=" * 66)
    print("  BMV Trading — SuperModel + Gemini + Risk Engine")
    print("=" * 66 + "\n")

    data, macro = load_data()
    if not data:
        raise SystemExit("Sin datos BMV suficientes.")

    if args.legacy:
        print("  Modo legacy: Ensemble v1\n")
        run_legacy(data, macro, args.capital)
        return

    print("\nDetectando régimen (HMM)...")
    regime_preview = detect_regime_hmm(macro)
    regime_preview["market_riskon"] = market_is_riskon(macro.get("NAFTRAC"))
    mkt = "🟢 RISK-ON" if regime_preview["market_riskon"] else "🔴 RISK-OFF"
    print(f"  {regime_preview.get('state','?').upper()}  |  {mkt}")

    print("\nEjecutando SuperModel (4 modelos + stacking)...")
    context = fetch_market_context()

    output, path = generate_bmv_signals(
        data, macro, args.capital,
        use_gemini=not args.no_gemini,
        use_stacking=not args.no_stacking,
        context=context,
    )

    gs = output["meta"].get("gemini_summary", {})
    if gs:
        print(f"\n  Gemini: CONFIRMA {gs.get('confirma',0)} · "
              f"DEGRADA {gs.get('degrada',0)} · VETA {gs.get('veta',0)}")

    print_signals(output["signals"], output["summary"], args.capital, output["regime"])
    print(f"  Guardado: {path}")
    print(f"  InsightsBundle: {ROOT / 'data' / 'insights_today.json'}\n")


if __name__ == "__main__":
    main()
