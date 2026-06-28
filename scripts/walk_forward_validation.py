"""
Walk-Forward Validation del modelo cross-seccional v2a.

Metodología expanding window:
  - Ventana 1: entrena 2008-2015  → testea 2016
  - Ventana 2: entrena 2008-2016  → testea 2017
  - ...
  - Ventana 9: entrena 2008-2023  → testea 2024

Incluye deliberadamente años difíciles:
  - 2018: caída de mercados emergentes
  - 2020: COVID (crash -35% en semanas)
  - 2022: mercado bajista global

Ejecución:
    python scripts/walk_forward_validation.py
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

from scripts.cross_sectional_backtest import (
    build_cross_sectional, run_backtest, TOP_N, COMM
)
from scripts.cross_sectional_v2 import add_rank_normalized, RN_COLS, _LGBM_BASE

HORIZON   = 20   # mensual
COST      = 0.0010  # 0.10%/lado — realista en GBM con algo de negociación
TEST_YEARS = list(range(2016, 2025))  # 9 años de test


def sharpe_year(period_rets: list[float]) -> float:
    pr = np.array(period_rets)
    ppy = 252 / HORIZON
    return float(pr.mean() / (pr.std() + 1e-9) * np.sqrt(ppy)) if len(pr) > 1 else 0.0


def main():
    print("\n" + "=" * 72)
    print("  WALK-FORWARD VALIDATION  |  v2a regresor rank-norm  |  mensual")
    print("  Test año por año con entrenamiento expandido (expanding window)")
    print("=" * 72)

    print("\nCargando datos...")
    df_all = build_cross_sectional(HORIZON).sort_index()
    df_all = add_rank_normalized(df_all)
    print(f"  {len(df_all):,} obs  |  {df_all['ticker'].nunique()} tickers  "
          f"|  {df_all.index.min().date()} → {df_all.index.max().date()}\n")

    results = []

    header = (f"  {'Año test':>9}  {'Meses':>6}  {'Ret LS':>8}  {'Sharpe LS':>10}  "
              f"{'Ret LO':>8}  {'Sharpe LO':>10}  {'NAFTRAC':>8}  Contexto")
    print(header)
    print("  " + "-" * 78)

    eq_ls = eq_lo = eq_bh = 10_000  # capital inicial para curva acumulada

    for year in TEST_YEARS:
        train = df_all[df_all.index.year < year]
        test  = df_all[df_all.index.year == year]

        if len(train) < 500 or len(test) < 20:
            continue

        reg = lgb.LGBMRegressor(**_LGBM_BASE)
        reg.fit(train[RN_COLS].values, train["pct_fwd"].values)

        t = test.copy()
        t["p_rel"] = reg.predict(test[RN_COLS].values)

        r = run_backtest(t, HORIZON, TOP_N, cost_mult=COST / COMM)
        ls = r["long_short"]
        lo = r["long_only"]
        bh = r["naftrac_bh"]

        # Contexto del año
        naf_ret = bh["total_ret"]
        ctx = ("🔴 crisis COVID" if year == 2020
               else "🔴 bear market" if year == 2022
               else "🟡 caída EM"   if year == 2018
               else "🟢 alcista"    if naf_ret > 8
               else "🟡 lateral")

        print(f"  {year:>9}  {ls['n_periods']:>6}  "
              f"{ls['total_ret']:>+7.1f}%  {ls['sharpe']:>10.2f}  "
              f"{lo['total_ret']:>+7.1f}%  {lo['sharpe']:>10.2f}  "
              f"{bh['total_ret']:>+7.1f}%  {ctx}")

        eq_ls *= (1 + ls["total_ret"] / 100)
        eq_lo *= (1 + lo["total_ret"] / 100)
        eq_bh *= (1 + bh["total_ret"] / 100)

        results.append({
            "year": year,
            "ls_ret": ls["total_ret"],   "ls_sharpe": ls["sharpe"],
            "lo_ret": lo["total_ret"],   "lo_sharpe": lo["sharpe"],
            "bh_ret": bh["total_ret"],   "bh_sharpe": bh["sharpe"],
            "ls_wr":  ls["win_rate"],
        })

    if not results:
        print("Sin resultados."); return

    res = pd.DataFrame(results)
    print("\n" + "  " + "=" * 72)
    print("  RESUMEN 2016-2024 (9 años, costo 0.10%/lado, rebalanceo mensual)")
    print("  " + "=" * 72)

    def agg(col, agg="mean"):
        return res[col].mean() if agg == "mean" else res[col].median()

    ls_pos = (res["ls_ret"] > 0).sum()
    lo_pos = (res["lo_ret"] > 0).sum()
    bh_pos = (res["bh_ret"] > 0).sum()

    print(f"\n  {'':30s}  {'LONG-SHORT':>12}  {'LONG-ONLY':>12}  {'NAFTRAC':>10}")
    print(f"  {'Retorno medio anual':30s}  {agg('ls_ret'):>+11.1f}%  {agg('lo_ret'):>+11.1f}%  {agg('bh_ret'):>+9.1f}%")
    print(f"  {'Sharpe medio':30s}  {agg('ls_sharpe'):>12.2f}  {agg('lo_sharpe'):>12.2f}  {agg('bh_sharpe'):>10.2f}")
    print(f"  {'Años positivos / 9':30s}  {ls_pos:>11}/9  {lo_pos:>11}/9  {bh_pos:>9}/9")
    print(f"  {'Capital final ($10,000)':30s}  ${eq_ls:>10,.0f}  ${eq_lo:>10,.0f}  ${eq_bh:>9,.0f}")
    print(f"\n  {'Peor año (Ret)':30s}  {res['ls_ret'].min():>+11.1f}%  {res['lo_ret'].min():>+11.1f}%  {res['bh_ret'].min():>+9.1f}%")
    print(f"  {'Mejor año (Ret)':30s}  {res['ls_ret'].max():>+11.1f}%  {res['lo_ret'].max():>+11.1f}%  {res['bh_ret'].max():>+9.1f}%")

    verdict_ls = "ROBUSTO ✓" if ls_pos >= 7 and agg("ls_sharpe") > 0.5 else "FRÁGIL ✗"
    verdict_lo = "ROBUSTO ✓" if lo_pos >= 7 and agg("lo_sharpe") > 0.4 else "FRÁGIL ✗"
    print(f"\n  Veredicto LONG-SHORT: {verdict_ls}")
    print(f"  Veredicto LONG-ONLY:  {verdict_lo}")
    print("  " + "=" * 72 + "\n")


if __name__ == "__main__":
    main()
