"""
Experimentos de mejora — prueba 3 palancas sobre el stack completo
(Ensemble + Meta-labeling + filtro de régimen):

  PALANCA 1 — Horizonte:        ¿operar a 5, 10 o 15 días reduce el ruido/costos?
  PALANCA 2 — Datos nuevos:     ¿agregar VIX (volatilidad implícita US) mejora?
  PALANCA 3 — Ventana de train: ¿entrenar solo con años recientes (régimen actual)?

Cada configuración se evalúa con un backtest semanal walk-forward sobre el
20% final (test fijo), rebalanceando cada `horizon/5` semanas para no solapar.

Ejecución:
    python scripts/experiments.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from scripts.run_meta     import build_dataset, PRIMARY_THRESH, COMM
from scripts.backtest_meta import market_riskon_weeks
from src.ml.features      import FEATURE_COLS
from src.ml.ensemble      import EnsembleModel
from src.ml.meta_model    import MetaModel
from src.ml.labeling      import sample_uniqueness_weights

TRAIN_RATIO   = 0.80
MAX_SIGNALS   = 5
CAPITAL       = 100_000
META_QUANTILE = 0.70   # selectividad fija para comparar configs de forma justa


# ── Backtest generalizado (rebalanceo cada step_weeks) ──────────────────────────

def weekly_backtest(test: pd.DataFrame, horizon: int,
                    score_floor: float | None,
                    allowed_weeks: set | None) -> dict:
    """Portafolio top-N, rankeado por meta, rebalanceando cada horizon/5 semanas."""
    step = max(1, round(horizon / 5))
    test = test.copy()
    test["week"] = test.index.to_period("W")
    weeks = sorted(test["week"].unique())

    equity = CAPITAL
    curve, period_rets, trade_rets = [], [], []
    n_traded = 0

    for wi, week in enumerate(weeks):
        if wi % step != 0:
            continue
        if allowed_weeks is not None and week not in allowed_weeks:
            period_rets.append(0.0)
            curve.append({"week": str(week), "equity": round(equity, 2), "n": 0})
            continue

        grp = test[test["week"] == week]
        last_per_ticker = grp.sort_index().groupby("ticker").tail(1)
        cand = last_per_ticker[last_per_ticker["p_up"] >= PRIMARY_THRESH]
        if score_floor is not None:
            cand = cand[cand["p_meta"] >= score_floor]
        cand = cand.sort_values("p_meta", ascending=False).head(MAX_SIGNALS)

        if len(cand) > 0:
            rets = cand["tb_ret"].values / 100.0 - COMM * 2
            pret = float(np.mean(rets))
            trade_rets.extend(rets.tolist())
            n_traded += 1
        else:
            pret = 0.0
        equity *= (1 + pret)
        period_rets.append(pret)
        curve.append({"week": str(week), "equity": round(equity, 2), "n": int(len(cand))})

    period_rets = np.array(period_rets)
    trade_rets  = np.array(trade_rets)
    ppy = 252 / horizon  # períodos por año
    total_ret = (equity / CAPITAL - 1) * 100
    sharpe = (period_rets.mean() / (period_rets.std() + 1e-9) * np.sqrt(ppy)) \
             if len(period_rets) > 1 else 0
    eq = np.array([c["equity"] for c in curve])
    dd = (eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq) if len(eq) else np.array([0])

    return {
        "total_ret":     round(float(total_ret), 2),
        "sharpe":        round(float(sharpe), 3),
        "max_dd":        round(float(dd.min() * 100), 2),
        "n_periods":     int(n_traded),
        "n_trades":      int(len(trade_rets)),
        "trade_win_rate": round(float((trade_rets > 0).mean()), 3) if len(trade_rets) else 0,
        "final_equity":  round(float(equity), 2),
    }


def train_eval(df: pd.DataFrame, feature_cols: list[str], horizon: int,
               train_start: pd.Timestamp | None = None,
               use_regime: bool = True, use_mlp: bool = False,
               mlp_seed: int = 42) -> dict:
    """Entrena primario + meta y corre el backtest con filtro de régimen."""
    df = df.sort_index()
    cut_date = df.index[int(len(df) * TRAIN_RATIO)]
    train = df[df.index < cut_date]
    if train_start is not None:
        train = train[train.index >= train_start]
    test = df[df.index >= cut_date]

    primary = EnsembleModel(top_features=15, calibrate=True,
                            use_mlp=use_mlp, mlp_seed=mlp_seed)
    primary.fit(train, feature_cols=feature_cols, target_col="y")
    p_tr = primary.predict_proba(train, feature_cols)
    p_te = primary.predict_proba(test,  feature_cols)
    auc_p = roc_auc_score(test["y"], p_te) if test["y"].nunique() > 1 else 0.5

    w = sample_uniqueness_weights(train["tb_bars"], horizon=horizon)
    meta = MetaModel()
    meta.fit(train, feature_cols=feature_cols, primary_proba=p_tr,
             meta_label=train["y"].values, sample_weight=w.values)
    pm_te = meta.predict_proba(test, feature_cols, primary_proba=p_te)

    test = test.copy()
    test["p_up"], test["p_meta"] = p_te, pm_te

    cand_meta = pm_te[p_te >= PRIMARY_THRESH]
    floor = float(np.quantile(cand_meta, META_QUANTILE)) if len(cand_meta) else None
    allowed = market_riskon_weeks(ma_window=20) if use_regime else None

    res = weekly_backtest(test, horizon=horizon, score_floor=floor, allowed_weeks=allowed)
    res["auc_primary"] = round(float(auc_p), 4)
    res["auc_meta"]    = round(float(meta.auc), 4)
    res["n_train"]     = int(len(train))
    res["train_start"] = str(train.index.min().date())
    return res


# ── VIX feature (palanca 2) ─────────────────────────────────────────────────────

def fetch_vix() -> pd.Series | None:
    """Descarga VIX y devuelve el cierre diario."""
    try:
        v = yf.download("^VIX", start="2007-01-01", progress=False, auto_adjust=False)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.get_level_values(0)
        return v["Close"]
    except Exception as e:
        print(f"  VIX download falló: {e}")
        return None


def add_vix_feature(df: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    """Agrega features de VIX: nivel z-score y cambio 5d."""
    df = df.copy()
    vix_aligned = vix.reindex(df.index, method="ffill")
    vix_ma = vix_aligned.rolling(50).mean()
    vix_sd = vix_aligned.rolling(50).std()
    df["vix_z"]    = (vix_aligned - vix_ma) / (vix_sd + 1e-8)
    df["vix_ret5"] = vix_aligned.pct_change(5) * 100
    return df


def fmt(r: dict) -> str:
    return (f"AUC_p={r['auc_primary']:.4f} AUC_m={r['auc_meta']:.4f}  "
            f"trades={r['n_trades']:>4}  WR={r['trade_win_rate']*100:>4.0f}%  "
            f"Sharpe={r['sharpe']:>5.2f}  MaxDD={r['max_dd']:>6.1f}%  "
            f"TotalRet={r['total_ret']:>+7.1f}%")


def main():
    print("\n" + "=" * 78)
    print("  EXPERIMENTOS DE MEJORA  |  stack = Ensemble + Meta + Régimen")
    print("=" * 78)

    results = {}

    # ════════════════════════════════════════════════════════════════════════════
    # PALANCA 1 — Horizonte
    # ════════════════════════════════════════════════════════════════════════════
    print("\n[PALANCA 1] Horizonte de la operación (5 / 10 / 15 días)\n")
    lever1 = {}
    datasets = {}  # cache para reusar horizonte 5
    for h in [5, 10, 15]:
        df = build_dataset(horizon=h)
        datasets[h] = df
        r = train_eval(df, FEATURE_COLS, horizon=h)
        lever1[f"h{h}"] = r
        print(f"  Horizonte {h:>2}d:  {fmt(r)}")
    results["lever1_horizon"] = lever1

    # Mejor horizonte para usar en las siguientes palancas
    best_h = max(lever1, key=lambda k: lever1[k]["total_ret"])
    best_h_val = int(best_h[1:])
    print(f"\n  → Mejor horizonte: {best_h_val} días ({lever1[best_h]['total_ret']:+.1f}%)")

    # ════════════════════════════════════════════════════════════════════════════
    # PALANCA 2 — Datos nuevos: VIX
    # ════════════════════════════════════════════════════════════════════════════
    print("\n[PALANCA 2] Agregar VIX (volatilidad implícita de EE.UU.)\n")
    lever2 = {}
    df5 = datasets[5]
    base5 = train_eval(df5, FEATURE_COLS, horizon=5)
    lever2["sin_vix"] = base5
    print(f"  Sin VIX:  {fmt(base5)}")

    vix = fetch_vix()
    if vix is not None:
        df5_vix = add_vix_feature(df5, vix).dropna(subset=["vix_z", "vix_ret5"])
        feats_vix = FEATURE_COLS + ["vix_z", "vix_ret5"]
        r_vix = train_eval(df5_vix, feats_vix, horizon=5)
        lever2["con_vix"] = r_vix
        print(f"  Con VIX:  {fmt(r_vix)}")
        d_auc = r_vix["auc_primary"] - base5["auc_primary"]
        d_ret = r_vix["total_ret"]  - base5["total_ret"]
        print(f"\n  → Δ AUC primario: {d_auc:+.4f}   Δ Retorno: {d_ret:+.1f} puntos")
    results["lever2_vix"] = lever2

    # ════════════════════════════════════════════════════════════════════════════
    # PALANCA 3 — Ventana de entrenamiento (recencia)
    # ════════════════════════════════════════════════════════════════════════════
    print("\n[PALANCA 3] Ventana de entrenamiento (entrenar con años recientes)\n")
    lever3 = {}
    for start_year in [None, 2016, 2019, 2021]:
        ts = pd.Timestamp(f"{start_year}-01-01") if start_year else None
        label = f"desde {start_year}" if start_year else "todo (2008+)"
        r = train_eval(df5, FEATURE_COLS, horizon=5, train_start=ts)
        lever3[label] = r
        print(f"  {label:<14}: {fmt(r)}  (n_train={r['n_train']:,})")
    results["lever3_window"] = lever3

    best_w = max(lever3, key=lambda k: lever3[k]["total_ret"])
    print(f"\n  → Mejor ventana: {best_w} ({lever3[best_w]['total_ret']:+.1f}%)")

    # ════════════════════════════════════════════════════════════════════════════
    # RESUMEN
    # ════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  RESUMEN — mejor de cada palanca vs baseline (horizonte 5, todo, sin VIX)")
    print("=" * 78)
    baseline_ret = base5["total_ret"]
    print(f"\n  Baseline (h5, 2008+, sin VIX):  {baseline_ret:+.1f}%")
    print(f"  P1 mejor horizonte ({best_h_val}d):     {lever1[best_h]['total_ret']:+.1f}%")
    if "con_vix" in lever2:
        print(f"  P2 con VIX:                     {lever2['con_vix']['total_ret']:+.1f}%")
    print(f"  P3 mejor ventana ({best_w}):  {lever3[best_w]['total_ret']:+.1f}%")

    out_path = ROOT / "data" / "experiments.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Guardado: {out_path}\n" + "=" * 78 + "\n")


if __name__ == "__main__":
    main()
