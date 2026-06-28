"""
VÍA A · v2 — Iteración para ENSANCHAR el alfa cross-seccional.

Tres mejoras sobre v1 (clasificación binaria "¿le gana a la mediana?"):

  1. Rank-normalización cross-seccional de TODAS las features (percentil dentro
     del universo cada día). Enfoca el modelo en posición relativa, no niveles
     absolutos. (Gu, Kelly & Xiu normalizan así las características.)
  2. Learning-to-rank: LGBMRanker con objetivo lambdarank, agrupado por fecha,
     que optimiza directamente el ORDEN (NDCG) — no la clasificación binaria.
  3. Target continuo: percentil del retorno futuro (LGBMRegressor) como
     alternativa al ranker.

Compara v1 (binario) vs v2-regresor vs v2-ranker por spread de quintil y Sharpe
del long-short, a horizonte mensual (el viable por turnover).

Ejecución:
    python scripts/cross_sectional_v2.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.ml.features import FEATURE_COLS
from src.ml.ensemble import EnsembleModel
from scripts.cross_sectional_backtest import build_cross_sectional, run_backtest, TRAIN_RATIO, TOP_N, COMM

# Features rank-normalizadas (percentil cross-seccional por fecha)
RN_COLS = [f"rn_{c}" for c in FEATURE_COLS]

_LGBM_BASE = dict(n_estimators=300, num_leaves=31, learning_rate=0.03,
                  min_child_samples=40, feature_fraction=0.7, bagging_fraction=0.8,
                  bagging_freq=1, reg_lambda=5.0, n_jobs=2, random_state=42, verbosity=-1)


def add_rank_normalized(df: pd.DataFrame) -> pd.DataFrame:
    """Añade rn_<feat> = percentil cross-seccional [0,1] de cada feature por fecha."""
    df = df.copy()
    g = df.groupby(df.index)
    for c in FEATURE_COLS:
        df[f"rn_{c}"] = g[c].rank(pct=True)
    # target continuo: percentil del retorno futuro dentro del universo ese día
    df["pct_fwd"] = g["fwd_ret"].rank(pct=True)
    df["rel_decile"] = (df["pct_fwd"] * 9.999).astype(int).clip(0, 9)  # relevancia 0-9
    return df


def group_sizes(idx: pd.DatetimeIndex) -> np.ndarray:
    """Tamaños de grupo (nº de tickers por fecha) para LGBMRanker, en orden de aparición."""
    s = pd.Series(1, index=idx).groupby(level=0).sum()
    return s.values


def quintile_spread(test: pd.DataFrame) -> float:
    q = test.groupby(pd.qcut(test["p_rel"].rank(method="first"), 5, labels=[1,2,3,4,5]))["fwd_ret"].mean()
    return float(q[5] - q[1]), q


def eval_strategy(name: str, test: pd.DataFrame, h: int):
    sp, q = quintile_spread(test)
    print(f"\n  [{name}]  spread Q5−Q1 = {sp:+.3f}%  "
          f"(Q1={q[1]:+.3f}  Q3={q[3]:+.3f}  Q5={q[5]:+.3f})  "
          f"{'✓' if sp>0 else 'INVERTIDO ✗'}")
    gross = run_backtest(test, h, TOP_N, cost_mult=0.0)
    print(f"    LONG-SHORT bruto:  Ret={gross['long_short']['total_ret']:+.1f}%  "
          f"Sharpe={gross['long_short']['sharpe']:.2f}  WR={gross['long_short']['win_rate']:.1f}%")
    print(f"    {'costo/lado':>10}  {'LONG-SHORT':>16}  {'LONG-ONLY':>16}")
    for c in [0.0005, 0.0010, 0.0015]:
        r = run_backtest(test, h, TOP_N, cost_mult=c / COMM)
        print(f"    {c*100:>9.2f}%  {r['long_short']['sharpe']:>6.2f} | {r['long_short']['total_ret']:>+6.1f}%  "
              f"{r['long_only']['sharpe']:>6.2f} | {r['long_only']['total_ret']:>+6.1f}%")
    return sp, gross['long_short']['sharpe']


def run_horizon(h: int):
    print("\n" + "=" * 82)
    print(f"  ITERACIÓN v2 — HORIZONTE {h}d ({'mensual' if h>=20 else 'semanal'})")
    print("=" * 82)

    df = build_cross_sectional(h).sort_index()
    df = add_rank_normalized(df)
    cut = df.index[int(len(df) * TRAIN_RATIO)]
    train, test = df[df.index < cut], df[df.index >= cut]

    # ── v1: EnsembleModel binario (baseline) ─────────────────────────────────
    m1 = EnsembleModel(top_features=15, calibrate=True)
    m1.fit(train, feature_cols=FEATURE_COLS, target_col="y_rel")
    t1 = test.copy(); t1["p_rel"] = m1.predict_proba(test, FEATURE_COLS)
    eval_strategy("v1 binario (baseline)", t1, h)

    # ── v2a: LGBMRegressor sobre percentil con features rank-normalizadas ─────
    reg = lgb.LGBMRegressor(**_LGBM_BASE)
    reg.fit(train[RN_COLS].values, train["pct_fwd"].values)
    t2 = test.copy(); t2["p_rel"] = reg.predict(test[RN_COLS].values)
    eval_strategy("v2a regresor-percentil (rank-norm)", t2, h)

    # ── v2b: LGBMRanker lambdarank agrupado por fecha ────────────────────────
    tr_sorted = train.sort_index()
    rk = lgb.LGBMRanker(objective="lambdarank", **_LGBM_BASE)
    rk.fit(tr_sorted[RN_COLS].values, tr_sorted["rel_decile"].values,
           group=group_sizes(tr_sorted.index))
    t3 = test.copy(); t3["p_rel"] = rk.predict(test[RN_COLS].values)
    eval_strategy("v2b ranker lambdarank (rank-norm)", t3, h)


def robustness_check(h: int = 20, n_seeds: int = 10):
    """v2a (regresor-percentil rank-norm) a través de varios seeds — ¿es estable o suerte?"""
    print("\n" + "=" * 82)
    print(f"  ROBUSTEZ v2a — {n_seeds} seeds, horizonte {h}d, costo 0.10%/lado")
    print("=" * 82)
    df = build_cross_sectional(h).sort_index()
    df = add_rank_normalized(df)
    cut = df.index[int(len(df) * TRAIN_RATIO)]
    train, test = df[df.index < cut], df[df.index >= cut]

    ls_sharpes, lo_sharpes, ls_rets = [], [], []
    for seed in range(n_seeds):
        params = {**_LGBM_BASE, "random_state": seed}
        reg = lgb.LGBMRegressor(**params)
        reg.fit(train[RN_COLS].values, train["pct_fwd"].values)
        t = test.copy(); t["p_rel"] = reg.predict(test[RN_COLS].values)
        r = run_backtest(t, h, TOP_N, cost_mult=0.0010 / COMM)
        ls_sharpes.append(r["long_short"]["sharpe"])
        lo_sharpes.append(r["long_only"]["sharpe"])
        ls_rets.append(r["long_short"]["total_ret"])

    ls, lo = np.array(ls_sharpes), np.array(lo_sharpes)
    print(f"\n  LONG-SHORT Sharpe:  media={ls.mean():.2f}  std={ls.std():.2f}  "
          f"min={ls.min():.2f}  max={ls.max():.2f}")
    print(f"  LONG-ONLY  Sharpe:  media={lo.mean():.2f}  std={lo.std():.2f}  "
          f"min={lo.min():.2f}  max={lo.max():.2f}")
    print(f"  LONG-SHORT Ret total: media={np.mean(ls_rets):+.1f}%  "
          f"min={np.min(ls_rets):+.1f}%  max={np.max(ls_rets):+.1f}%")
    veredicto = "ROBUSTO ✓ (alfa real)" if lo.mean() > 0.6 and lo.min() > 0.2 else "FRÁGIL — depende de seed"
    print(f"\n  Veredicto: {veredicto}")


def main():
    print("\n" + "=" * 82)
    print("  ITERAR EL ALFA CROSS-SECCIONAL  |  rank-norm + learning-to-rank")
    print("=" * 82)
    run_horizon(20)
    run_horizon(5)
    robustness_check(h=20, n_seeds=10)
    print()


if __name__ == "__main__":
    main()
