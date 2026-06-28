"""
¿Agregar fundamentales (estados financieros) mejora el modelo?

Compara el stack de producción (Ensemble + Meta + filtro de régimen) con y sin
las 5 features fundamentales (márgenes + crecimiento YoY) sobre el hold-out 20%.

Los fundamentales se integran con merge_asof sobre available_date
(fin de trimestre + 70 días de lag de publicación) → SIN look-ahead.

Ejecución:
    python scripts/fundamentals_backtest.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.data.store   import get as store_get, BMV_TICKERS, MACRO_TICKERS
from src.ml.features  import (compute_features, add_macro_features,
                              add_cross_section_features, add_fundamental_features,
                              FEATURE_COLS, FUNDAMENTAL_FEATURE_COLS)
from src.ml.labeling  import triple_barrier_labels
from scripts.experiments import train_eval, fmt
from scripts.run_meta    import HORIZON, MULT_TARGET, MULT_STOP

FUND_PATH = ROOT / "data" / "fundamentals.parquet"

FUND_RANK_COLS = ["fund_margin_rank", "fund_quality_rank",
                  "fund_growth_rank", "fund_revgrow_rank"]


def load_fundamentals() -> dict[str, pd.DataFrame]:
    """Carga fundamentals.parquet → dict ticker → DataFrame (indexado por quarter_end)."""
    if not FUND_PATH.exists():
        print(f"ERROR: no existe {FUND_PATH}. Corre primero scripts/fetch_fundamentals.py")
        sys.exit(1)
    raw = pd.read_parquet(FUND_PATH)
    out = {}
    for ticker, grp in raw.groupby("ticker"):
        g = grp.set_index("quarter_end").sort_index()
        out[ticker] = g
    return out


def build_dataset_with_fund(horizon: int = HORIZON) -> pd.DataFrame:
    """Igual que run_meta.build_dataset pero inyectando features fundamentales."""
    macro = {n: store_get(n) for n in MACRO_TICKERS}
    macro = {k: v for k, v in macro.items() if v is not None}
    funds = load_fundamentals()

    feat_frames = {}
    for ticker in BMV_TICKERS:
        raw = store_get(ticker)
        if raw is None or len(raw) < 200:
            continue
        try:
            feat = compute_features(raw)
            feat = add_macro_features(feat, macro)
            feat = add_fundamental_features(feat, funds.get(ticker))

            vol = (feat["atr_pct"] / 100.0) if "atr_pct" in feat.columns else \
                  raw["Close"].pct_change().rolling(14).std()
            tb = triple_barrier_labels(
                close=raw["Close"], high=raw["High"], low=raw["Low"],
                vol=vol, horizon=horizon,
                mult_target=MULT_TARGET, mult_stop=MULT_STOP,
            )
            feat["y"]       = tb["label"]
            feat["tb_ret"]  = tb["ret"]
            feat["tb_bars"] = tb["bars"]
            feat["touch"]   = tb["touch"]
            feat["ticker"]  = ticker
            feat_frames[ticker] = feat
        except Exception as e:
            print(f"  {ticker}: {e}")

    feat_frames = add_cross_section_features(feat_frames)

    # Ranks cross-seccionales de fundamentales (value/quality relativo al universo).
    # Esto evita el problema de "dummy de ticker": en vez del nivel absoluto del
    # margen (casi constante por trimestre), usa el percentil vs los pares ese día.
    base_fund = ["fund_net_margin", "fund_oper_margin", "fund_earnings_yoy", "fund_revenue_yoy"]
    panels = {f: pd.DataFrame({t: feat_frames[t][f] for t in feat_frames if f in feat_frames[t].columns})
              for f in base_fund}
    ranks = {f: panels[f].rank(axis=1, pct=True, na_option="keep") for f in base_fund}
    for t in feat_frames:
        feat_frames[t]["fund_margin_rank"]   = ranks["fund_net_margin"].get(t, pd.Series(index=feat_frames[t].index))
        feat_frames[t]["fund_quality_rank"]  = ranks["fund_oper_margin"].get(t, pd.Series(index=feat_frames[t].index))
        feat_frames[t]["fund_growth_rank"]   = ranks["fund_earnings_yoy"].get(t, pd.Series(index=feat_frames[t].index))
        feat_frames[t]["fund_revgrow_rank"]  = ranks["fund_revenue_yoy"].get(t, pd.Series(index=feat_frames[t].index))

    df = pd.concat(feat_frames.values()).sort_index()

    # Rellenar NaN de fundamentales con valor neutral (banks + pre-publicación)
    # para no descartar filas y comparar de forma justa contra el modelo base.
    for col in FUNDAMENTAL_FEATURE_COLS:
        if "yoy" in col:
            df[col] = df[col].fillna(0.0)              # crecimiento desconocido → neutral
        else:
            df[col] = df[col].fillna(df[col].median())  # margen desconocido → mediana
    for col in FUND_RANK_COLS:
        df[col] = df[col].fillna(0.5)                  # rank desconocido → mediana del universo
    return df


def coverage_report(df: pd.DataFrame):
    """Qué % de filas tiene fundamentales reales (no rellenados)."""
    print("\n  Cobertura de fundamentales (filas con dato real publicado):")
    df = df.sort_index()
    cut = df.index[int(len(df) * 0.80)]
    test = df[df.index >= cut]
    real = (test["fund_net_margin"] != test["fund_net_margin"].median()).mean()
    print(f"    Test: {len(test):,} filas  |  ~{real*100:.0f}% con margen real")


def main():
    print("\n" + "=" * 78)
    print("  ¿MEJORAN LOS FUNDAMENTALES?  |  stack = Ensemble + Meta + Régimen")
    print("=" * 78)

    print("\n[1] Construyendo dataset con fundamentales (merge_asof, lag 70d)...")
    df = build_dataset_with_fund(horizon=HORIZON)
    # dataset base: dropna solo sobre FEATURE_COLS (igual que run_meta)
    df_base = df.dropna(subset=FEATURE_COLS + ["y"]).copy()
    print(f"    {len(df_base):,} observaciones")
    coverage_report(df_base)

    feats_with_fund = FEATURE_COLS + FUNDAMENTAL_FEATURE_COLS
    df_fund = df.dropna(subset=feats_with_fund + ["y"]).copy()

    print("\n[2] BASE (solo técnicas + macro + cross-section):")
    r_base = train_eval(df_base, FEATURE_COLS, horizon=HORIZON)
    print(f"    {fmt(r_base)}")

    print("\n[3] + FUNDAMENTALES NIVEL (márgenes + crecimiento YoY absolutos):")
    r_fund = train_eval(df_fund, feats_with_fund, horizon=HORIZON)
    print(f"    {fmt(r_fund)}")

    print("\n[4] + FUNDAMENTALES RANK (value/quality cross-seccional vs universo):")
    feats_with_rank = FEATURE_COLS + FUND_RANK_COLS
    df_rank = df.dropna(subset=feats_with_rank + ["y"]).copy()
    r_rank = train_eval(df_rank, feats_with_rank, horizon=HORIZON)
    print(f"    {fmt(r_rank)}")

    def delta(r, name):
        print(f"\n  {name}")
        print(f"    Δ AUC primario:  {r['auc_primary'] - r_base['auc_primary']:+.4f}")
        print(f"    Δ AUC meta:      {r['auc_meta']    - r_base['auc_meta']:+.4f}")
        print(f"    Δ Sharpe:        {r['sharpe']    - r_base['sharpe']:+.3f}")
        print(f"    Δ Retorno total: {r['total_ret'] - r_base['total_ret']:+.1f} pts")

    print("\n" + "=" * 78)
    print(f"  DELTAS vs BASE (base: AUC_p={r_base['auc_primary']:.4f}  Ret={r_base['total_ret']:+.1f}%)")
    print("=" * 78)
    delta(r_fund, "[3] Nivel absoluto:")
    delta(r_rank, "[4] Rank cross-seccional:")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
