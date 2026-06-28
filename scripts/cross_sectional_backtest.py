"""
VÍA A — Modelo CROSS-SECCIONAL long-short (market-neutral).

En vez de predecir "¿sube WALMEX?" (direccional, techo ~0.53 AUC), el modelo
predice "¿le gana esta acción al universo?" (rank relativo). Evidencia: Gu,
Kelly & Xiu (2020) — un long-short por deciles ordenado por ML da Sharpe ~1.35,
muy por encima del enfoque direccional.

Estrategia:
  - Target: y_rel = 1 si el retorno futuro del ticker > mediana del universo ese día.
  - Cada rebalanceo: LONG el top-N por p_rel, SHORT el bottom-N → dollar-neutral.
  - Retorno del período = media(longs) − media(shorts) − costos.

Comparado contra: long-only top-N y buy&hold de NAFTRAC (IPC).
Sin look-ahead: features en t, entrada Open[t+1], salida Close[t+1+h].

Ejecución:
    python scripts/cross_sectional_backtest.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.data.store  import get as store_get, BMV_TICKERS, MACRO_TICKERS
from src.ml.features import (compute_features, add_macro_features,
                             add_cross_section_features, compute_target, FEATURE_COLS)
from src.ml.ensemble import EnsembleModel

HORIZON     = 5         # días de holding (semanal)
TRAIN_RATIO = 0.80
TOP_N       = 5         # nombres por pata (long y short)
MIN_NAMES   = 10        # mínimo de tickers con dato ese día para rankear
COMM        = 0.0025    # comisión por lado
CAPITAL     = 100_000


def build_cross_sectional(horizon: int = HORIZON) -> pd.DataFrame:
    """Dataset panel con features + retorno futuro + target relativo cross-seccional."""
    macro = {n: store_get(n) for n in MACRO_TICKERS}
    macro = {k: v for k, v in macro.items() if v is not None}

    feat_frames = {}
    for ticker in BMV_TICKERS:
        raw = store_get(ticker)
        if raw is None or len(raw) < 200:
            continue
        try:
            feat = compute_features(raw)
            feat = add_macro_features(feat, macro)
            feat["fwd_ret"] = compute_target(raw, horizon=horizon, use_open_entry=True)
            feat["ticker"]  = ticker
            feat_frames[ticker] = feat
        except Exception as e:
            print(f"  {ticker}: {e}")

    feat_frames = add_cross_section_features(feat_frames)
    df = pd.concat(feat_frames.values()).sort_index()
    df = df.dropna(subset=FEATURE_COLS + ["fwd_ret"])

    # Target relativo: ¿le gana a la mediana del universo ese día?
    df["uni_n"]    = df.groupby(df.index)["fwd_ret"].transform("count")
    df["uni_med"]  = df.groupby(df.index)["fwd_ret"].transform("median")
    df = df[df["uni_n"] >= MIN_NAMES]
    df["y_rel"] = (df["fwd_ret"] > df["uni_med"]).astype(int)
    return df


def portfolio_metrics(period_rets: list[float], curve: list[float], horizon: int) -> dict:
    pr = np.array(period_rets)
    eq = np.array(curve)
    ppy = 252 / horizon
    total = (eq[-1] / eq[0] - 1) * 100 if len(eq) else 0
    sharpe = (pr.mean() / (pr.std() + 1e-9) * np.sqrt(ppy)) if len(pr) > 1 else 0
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([1])
    dd = ((eq - peak) / peak).min() * 100 if len(eq) else 0
    return {
        "total_ret": round(float(total), 2),
        "sharpe":    round(float(sharpe), 3),
        "max_dd":    round(float(dd), 2),
        "win_rate":  round(float((pr > 0).mean() * 100), 1) if len(pr) else 0,
        "n_periods": int(len(pr)),
        "avg_period": round(float(pr.mean() * 100), 3) if len(pr) else 0,
    }


def run_backtest(test: pd.DataFrame, horizon: int, top_n: int, cost_mult: float = 1.0) -> dict:
    """Long-short, long-only y NAFTRAC sobre el mismo calendario de rebalanceo."""
    step = max(1, round(horizon / 5))
    test = test.copy()
    test["week"] = test.index.to_period("W")
    weeks = sorted(test["week"].unique())

    naf = store_get("NAFTRAC")  # benchmark IPC

    eq_ls, eq_lo, eq_bh = CAPITAL, CAPITAL, CAPITAL
    c_ls, c_lo, c_bh, c_hed = [eq_ls], [eq_lo], [eq_bh], [CAPITAL]
    r_ls, r_lo, r_bh, r_hed = [], [], [], []

    for wi, week in enumerate(weeks):
        if wi % step != 0:
            continue
        grp = test[test["week"] == week]
        last = grp.sort_index().groupby("ticker").tail(1)
        if len(last) < MIN_NAMES:
            continue
        ranked = last.sort_values("p_rel", ascending=False)
        longs  = ranked.head(top_n)
        shorts = ranked.tail(top_n)

        long_ret  = longs["fwd_ret"].mean()  / 100.0
        short_ret = shorts["fwd_ret"].mean() / 100.0

        # Benchmark NAFTRAC en el mismo horizonte
        d0 = last.index.max()
        bh = 0.0
        if naf is not None:
            fut = naf["Close"][naf.index > d0]
            base = naf["Close"][naf.index <= d0]
            if len(fut) >= horizon and len(base) > 0:
                bh = float(fut.iloc[horizon - 1] / base.iloc[-1] - 1)

        # Long-short acciones (dollar-neutral, requiere shortear acciones): 4 patas
        ls = (long_ret - short_ret) - COMM * 4 * cost_mult
        # Long-only top-N: 2 patas
        lo = long_ret - COMM * 2 * cost_mult
        # Beta-hedged retail: LONG top-N acciones − SHORT NAFTRAC (índice sí shorteable)
        bh_hedged = (long_ret - bh) - COMM * 4 * cost_mult

        eq_ls *= (1 + ls); eq_lo *= (1 + lo); eq_bh *= (1 + bh)
        eq_hed = c_hed[-1] * (1 + bh_hedged)
        r_ls.append(ls); r_lo.append(lo); r_bh.append(bh); r_hed.append(bh_hedged)
        c_ls.append(eq_ls); c_lo.append(eq_lo); c_bh.append(eq_bh); c_hed.append(eq_hed)

    return {
        "long_short":  portfolio_metrics(r_ls, c_ls, horizon),
        "long_only":   portfolio_metrics(r_lo, c_lo, horizon),
        "hedged":      portfolio_metrics(r_hed, c_hed, horizon),
        "naftrac_bh":  portfolio_metrics(r_bh, c_bh, horizon),
    }


def eval_horizon(h: int):
    """Construye, entrena y backtestea el cross-seccional a un horizonte dado."""
    print("\n" + "=" * 80)
    print(f"  HORIZONTE {h} DÍAS  ({'semanal' if h<=5 else f'cada {h//5} semanas (~mensual)' if h>=20 else 'multi-día'})")
    print("=" * 80)

    df = build_cross_sectional(h).sort_index()
    cut = df.index[int(len(df) * TRAIN_RATIO)]
    train, test = df[df.index < cut], df[df.index >= cut]

    model = EnsembleModel(top_features=15, calibrate=True)
    model.fit(train, feature_cols=FEATURE_COLS, target_col="y_rel")
    p_test = model.predict_proba(test, FEATURE_COLS)
    auc = roc_auc_score(test["y_rel"], p_test) if test["y_rel"].nunique() > 1 else 0.5
    test = test.copy(); test["p_rel"] = p_test

    qm = test.groupby(pd.qcut(test["p_rel"].rank(method="first"), 5, labels=[1,2,3,4,5]))["fwd_ret"].mean()
    print(f"  AUC relativo={auc:.4f}  |  spread quintil Q5−Q1={qm[5]-qm[1]:+.3f}% "
          f"({'✓' if qm[5]>qm[1] else 'INVERTIDO ✗'})  |  test {test.index.min().date()}→{test.index.max().date()}")

    gross = run_backtest(test, h, TOP_N, cost_mult=0.0)
    g = gross["long_short"]
    print(f"\n  LONG-SHORT BRUTO:  Ret={g['total_ret']:+.1f}%  Sharpe={g['sharpe']:.2f}  "
          f"WR={g['win_rate']:.1f}%  bruto/período={g['avg_period']:+.3f}%  n={g['n_periods']}")

    print(f"\n  Sensibilidad a costos por estrategia (Sharpe neto | Ret total):")
    print(f"  {'costo/lado':>10}  {'LONG-SHORT':>16}  {'LONG+short NAFTRAC':>20}  {'LONG-ONLY':>16}")
    for c in [0.0, 0.0005, 0.0010, 0.0015, 0.0025]:
        r = run_backtest(test, h, TOP_N, cost_mult=c / COMM)
        ls_, hd_, lo_ = r["long_short"], r["hedged"], r["long_only"]
        print(f"  {c*100:>9.2f}%  {ls_['sharpe']:>6.2f} | {ls_['total_ret']:>+6.1f}%  "
              f"{hd_['sharpe']:>9.2f} | {hd_['total_ret']:>+6.1f}%  "
              f"{lo_['sharpe']:>6.2f} | {lo_['total_ret']:>+6.1f}%")

    bh = run_backtest(test, h, TOP_N, cost_mult=1.0)["naftrac_bh"]
    print(f"\n  Referencia NAFTRAC buy&hold: Ret={bh['total_ret']:+.1f}%  Sharpe={bh['sharpe']:.2f}  "
          f"(las estrategias hedged/LS son market-neutral → Sharpe aditivo al portafolio)")
    return g


def main():
    print("\n" + "=" * 80)
    print("  VÍA A — CROSS-SECCIONAL LONG-SHORT (market-neutral)")
    print("  Hallazgo: hay alfa BRUTO; la viabilidad depende de costo y turnover.")
    print("=" * 80)
    eval_horizon(5)    # semanal (alto turnover)
    eval_horizon(20)   # ~mensual (bajo turnover, como Gu-Kelly-Xiu)
    print()


if __name__ == "__main__":
    main()
