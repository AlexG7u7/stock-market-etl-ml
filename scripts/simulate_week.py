"""
Simulación de una semana histórica con EnsembleModel v1 + HMM.

Uso desde línea de comandos:
    python scripts/simulate_week.py --date 2026-06-20 --capital 5000

Uso desde Streamlit (app.py):
    from scripts.simulate_week import run_simulation
    result = run_simulation(signal_date="2026-06-20", capital=5000)
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.data.store     import get as store_get, BMV_TICKERS, MACRO_TICKERS
from src.ml.features    import compute_features, add_macro_features, FEATURE_COLS, add_cross_section_features, CROSS_SECTION_COLS
from src.ml.ensemble    import EnsembleModel
from src.ml.pipeline    import train_pipeline, market_is_riskon
from src.ml.regime      import RegimeDetector
from src.ml.risk_engine import build_signal, compute_correlation_matrix, correlation_penalty

HORIZON     = 5
PROB_THRESH = 0.53
KELLY_FRAC  = 0.25
MAX_POS     = 0.20
MAX_SIGNALS = 5


def run_simulation(
    signal_date: str,
    capital:     float = 5_000,
    verbose:     bool  = True,
) -> dict:
    """
    Simula las señales generadas el viernes `signal_date` y evalúa
    el resultado durante la semana siguiente.

    Args:
        signal_date: 'YYYY-MM-DD' del viernes de señales
        capital:     Capital en MXN
        verbose:     Si True, imprime el reporte

    Returns:
        dict con 'signals', 'results', 'summary', 'regime', 'all_preds'
    """
    cutoff    = pd.Timestamp(signal_date)
    entry_day = cutoff + pd.tseries.offsets.BDay(1)   # lunes siguiente
    settle    = cutoff + pd.tseries.offsets.BDay(5)   # viernes siguiente

    if verbose:
        print("=" * 65)
        print(f"  SIMULACIÓN  |  Señales: {cutoff.date()}  |  Capital: ${capital:,}")
        print(f"  Entrada: {entry_day.date()}  |  Cierre: {settle.date()}")
        print("=" * 65)

    # ── 1. Cargar datos hasta la fecha de señal ───────────────────────────────
    macro: dict[str, pd.DataFrame] = {}
    for name in MACRO_TICKERS:
        df = store_get(name)
        if df is not None:
            macro[name] = df[df.index <= cutoff].copy()

    raw: dict[str, pd.DataFrame] = {}
    for name in BMV_TICKERS:
        df = store_get(name)
        if df is not None and len(df[df.index <= cutoff]) >= 100:
            raw[name] = df[df.index <= cutoff].copy()

    if verbose:
        print(f"\n[1] {len(raw)} tickers cargados hasta {cutoff.date()}")

    # ── 2. Detectar régimen ───────────────────────────────────────────────────
    naftrac = macro.get("NAFTRAC")
    sp500   = macro.get("SP500")
    regime_info = {"state": "unknown", "proba": {}, "is_favorable": True}

    if naftrac is not None:
        try:
            det = RegimeDetector(n_states=3, n_iter=200)
            det.fit(naftrac, sp500)
            regime_info = {
                "state":        det.predict_current(naftrac, sp500),
                "proba":        {k: round(v, 3) for k, v in det.state_proba(naftrac, sp500).items()},
                "is_favorable": det.is_favorable(naftrac, sp500),
            }
        except Exception:
            pass

    # Filtro de régimen de mercado (NAFTRAC sobre su MA) — probado en backtest
    market_riskon = market_is_riskon(naftrac)
    regime_info["market_riskon"] = market_riskon

    if verbose:
        st = regime_info["state"]
        pr = regime_info["proba"]
        icon = {"bull": "✅", "lateral": "⚡", "bear": "⚠️"}.get(st, "❓")
        mkt = "🟢 RISK-ON" if market_riskon else "🔴 RISK-OFF (mercado bajo su MA20)"
        print(f"[2] Régimen: {icon} {st.upper()}  "
              f"bull={pr.get('bull',0):.0%}  bear={pr.get('bear',0):.0%}  |  {mkt}")

    # ── 3. Construir dataset de entrenamiento ─────────────────────────────────
    # 3a. Features individuales
    feat_frames: dict[str, pd.DataFrame] = {}
    for name, df in raw.items():
        try:
            feat = compute_features(df)
            feat = add_macro_features(feat, macro)
            feat["y"]      = (df["Close"].shift(-HORIZON) / df["Close"] - 1 > 0).astype(int)
            feat["ticker"] = name
            feat_frames[name] = feat
        except Exception:
            pass

    # 3b. Features cross-seccionales (ranking vs universo, sin look-ahead)
    feat_frames = add_cross_section_features(feat_frames)

    all_feature_cols = FEATURE_COLS  # ya incluye CROSS_SECTION_COLS

    rows = []
    for name, feat in feat_frames.items():
        available = [c for c in all_feature_cols if c in feat.columns]
        feat_clean = feat.dropna(subset=available + ["y"])
        if len(feat_clean) > 30:
            rows.append(feat_clean)

    if not rows:
        return {"error": "Sin datos suficientes", "signals": [], "results": [], "summary": {}}

    if verbose:
        n_obs = sum(len(r) for r in rows)
        print(f"[3] Entrenando pipeline (Ensemble + Meta-labeling) sobre {n_obs:,} obs "
              f"({len(feat_frames)} tickers, {len(FEATURE_COLS)} features)...")

    model = train_pipeline(
        feat_frames, raw, feature_cols=all_feature_cols,
        target_col="y", primary_thresh=PROB_THRESH, use_meta=True,
    )

    if verbose:
        print(f"    {model.primary.summary()}")
        if model.meta is not None:
            print(f"    Meta AUC={model.meta.auc:.4f}  cut={model.meta_cut:.3f}  "
                  f"precisión={model.meta.precision:.3f}")

    # ── 4. Predicciones para la fecha de señal ────────────────────────────────
    all_preds = []

    last_frames = {
        name: df.dropna(subset=[c for c in all_feature_cols if c in df.columns])
        for name, df in feat_frames.items()
        if len(df.dropna(subset=[c for c in all_feature_cols if c in df.columns])) > 0
    }

    for name, feat in last_frames.items():
        try:
            last = feat.iloc[[-1]]
            pred = model.predict_one(last)
            df   = raw[name]
            price = float(df["Close"].iloc[-1])
            atr14 = float(feat["_atr14"].iloc[-1]) if "_atr14" in feat.columns \
                    else price * 0.02
            all_preds.append({
                "ticker": name,
                "p_up":   pred["p_primary"],
                "p_meta": pred["p_meta"],
                "take":   pred["take"],
                "price":  price, "atr14": atr14,
            })
        except Exception:
            pass

    all_preds.sort(key=lambda x: x["p_up"], reverse=True)

    if verbose:
        print(f"\n[4] Top predicciones (primario≥{PROB_THRESH}, meta≥{model.meta_cut:.2f}):")
        for p in all_preds[:10]:
            marca = "✅ SEÑAL" if p.get("take") else "—"
            mp = f"meta={p['p_meta']*100:.0f}%" if p.get("p_meta") is not None else ""
            print(f"    {p['ticker']:<12}  P={p['p_up']*100:.1f}%  {mp:<10}  "
                  f"${p['price']:.2f}  {marca}")

    # ── 5. Aplicar risk engine ────────────────────────────────────────────────
    thresh = PROB_THRESH
    if regime_info.get("state") == "bear":
        thresh = 0.56

    returns_dict = {
        n: raw[n]["Close"].pct_change().dropna()
        for n in raw if "Close" in raw[n].columns
    }
    corr_matrix = compute_correlation_matrix(returns_dict, window=63)

    # Filtro de régimen de mercado: si el mercado está risk-off, no operar.
    if not market_riskon:
        if verbose:
            print("\n[5] 🔴 Mercado RISK-OFF (NAFTRAC bajo su MA20) — no se opera esta semana.")
        primary_candidates = []
    else:
        # Candidatos: sobre el umbral primario de régimen.
        # Se rankean por confianza del meta-modelo (si existe) — los trades que el
        # meta considera de mayor calidad van primero.
        primary_candidates = [p for p in all_preds if p["p_up"] >= thresh]
    has_meta = any(p.get("p_meta") is not None for p in primary_candidates)
    if has_meta:
        # Prioriza meta-aprobados, luego por p_meta, luego por p_up
        meta_candidates = sorted(
            primary_candidates,
            key=lambda p: (p.get("take", False), p.get("p_meta") or 0, p["p_up"]),
            reverse=True,
        )
    else:
        meta_candidates = primary_candidates

    signals_out, selected = [], []
    for p in meta_candidates:
        if len(signals_out) >= MAX_SIGNALS:
            break
        corr_f = correlation_penalty(p["ticker"], corr_matrix, selected)
        sig    = build_signal(
            ticker=p["ticker"], price=p["price"], atr=p["atr14"],
            p_up=p["p_up"], capital_mxn=capital,
            corr_factor=corr_f, features={},
            kelly_frac=KELLY_FRAC, max_position=MAX_POS,
        )
        if sig:
            signals_out.append(sig)
            selected.append(p["ticker"])

    # ── 6. Simular resultado real ─────────────────────────────────────────────
    results = []
    for s in signals_out:
        full_df = store_get(s.ticker)
        if full_df is None:
            continue
        week = full_df[
            (full_df.index >= entry_day) & (full_df.index <= settle)
        ]
        if len(week) == 0:
            continue

        entry_actual = float(week["Open"].iloc[0])
        settle_price = float(week["Close"].iloc[-1])
        week_high    = float(week["High"].max())
        week_low     = float(week["Low"].min())

        hit_stop = week_low  <= s.stop
        hit_t1   = week_high >= s.target_1
        hit_t2   = week_high >= s.target_2

        if hit_stop and not hit_t1:
            exit_price, exit_reason = s.stop, "STOP"
        elif hit_t2:
            exit_price, exit_reason = s.target_2, "TARGET 2"
        elif hit_t1:
            exit_price, exit_reason = s.target_1, "TARGET 1"
        else:
            exit_price, exit_reason = settle_price, "CIERRE"

        pnl_mxn  = (exit_price - entry_actual) * s.shares
        pnl_pct  = (exit_price - entry_actual) / entry_actual * 100
        invested = entry_actual * s.shares
        comision = invested * 0.0025 * 2
        pnl_net  = pnl_mxn - comision

        results.append({
            "ticker":       s.ticker,
            "p_up":         s.p_up,
            "entry_model":  s.entry,
            "entry_actual": round(entry_actual, 2),
            "stop":         s.stop,
            "target_1":     s.target_1,
            "target_2":     s.target_2,
            "week_low":     round(week_low, 2),
            "week_high":    round(week_high, 2),
            "exit_price":   round(exit_price, 2),
            "exit_reason":  exit_reason,
            "shares":       s.shares,
            "invested":     round(invested, 2),
            "pnl_mxn":      round(pnl_mxn, 2),
            "pnl_net":      round(pnl_net, 2),
            "pnl_pct":      round(pnl_pct, 2),
            "comision":     round(comision, 2),
            "hit_stop":     bool(hit_stop),
            "hit_t1":       bool(hit_t1),
            "hit_t2":       bool(hit_t2),
        })

    # ── 7. Resumen ────────────────────────────────────────────────────────────
    total_pnl = sum(r["pnl_net"] for r in results)
    total_inv = sum(r["invested"] for r in results)
    wins      = sum(1 for r in results if r["pnl_net"] > 0)

    summary = {
        "n_signals":    len(signals_out),
        "n_trades":     len(results),
        "n_wins":       wins,
        "win_rate":     round(wins / len(results), 3) if results else 0,
        "total_pnl":    round(total_pnl, 2),
        "total_inv":    round(total_inv, 2),
        "return_pct":   round(total_pnl / capital * 100, 2) if capital else 0,
        "final_capital": round(capital + total_pnl, 2),
        "signal_date":  str(cutoff.date()),
        "entry_date":   str(entry_day.date()),
        "settle_date":  str(settle.date()),
    }

    if verbose:
        print(f"\n{'='*65}")
        print(f"  RESULTADOS")
        print(f"{'='*65}")
        for r in results:
            icon = "✅" if r["pnl_net"] > 0 else "❌"
            print(f"  {icon} {r['ticker']:<10}  P={r['p_up']*100:.0f}%  "
                  f"entrada=${r['entry_actual']:.2f}  salida=${r['exit_price']:.2f}  "
                  f"→ {r['exit_reason']}  PnL=${r['pnl_net']:+.0f}")
        if not results:
            print("  Sin señales esta semana.")
        print(f"\n  Trades: {len(results)}  Wins: {wins}  "
              f"PnL: ${total_pnl:+,.0f}  Retorno: {summary['return_pct']:+.2f}%")

    return {
        "signals":   [
            {"ticker": s.ticker, "p_up": s.p_up, "price": s.price,
             "entry": s.entry, "stop": s.stop,
             "target_1": s.target_1, "target_2": s.target_2,
             "shares": s.shares, "capital_mxn": s.capital_mxn, "atr": s.atr}
            for s in signals_out
        ],
        "results":   results,
        "summary":   summary,
        "regime":    regime_info,
        "all_preds": all_preds[:25],
        "meta": {
            "uses_meta":   model.meta is not None,
            "meta_auc":    round(model.meta.auc, 4) if model.meta else None,
            "meta_cut":    round(model.meta_cut, 4),
            "primary_auc_lr":   round(model.primary.auc_lr, 4),
            "primary_auc_lgbm": round(model.primary.auc_lgbm, 4),
        },
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=str(date.today() - timedelta(days=7)),
                        help="Fecha de señal (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=5_000)
    args = parser.parse_args()

    result = run_simulation(signal_date=args.date, capital=args.capital, verbose=True)

    out_path = ROOT / "data" / "backtest_week.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\nGuardado: {out_path}")
