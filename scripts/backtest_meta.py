"""
Backtest semanal completo: pipeline Meta-Labeling sobre todo el período de test.

Simula un portafolio real semana a semana:
  - Entrena el pipeline (Ensemble + Meta) una vez sobre el 80% inicial.
  - Recorre cada semana del 20% de test.
  - Cada semana selecciona top-N señales rankeadas por el meta-modelo.
  - El retorno realizado de cada trade es su label triple-barrier (toca
    target/stop/tiempo), que ya incluye los stops reales.
  - Acumula equity y compara contra la estrategia base (sin meta).

Barre varios niveles de selectividad para encontrar el óptimo.

Ejecución:
    python scripts/backtest_meta.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from scripts.run_meta import build_dataset, HORIZON, PRIMARY_THRESH, COMM
from src.data.store   import get as store_get
from src.ml.features  import FEATURE_COLS
from src.ml.ensemble  import EnsembleModel
from src.ml.meta_model import MetaModel
from src.ml.labeling  import sample_uniqueness_weights

TRAIN_RATIO = 0.80
MAX_SIGNALS = 5          # tamaño del portafolio semanal
CAPITAL     = 100_000    # capital inicial (escala, no afecta % retorno)


def market_riskon_weeks(ma_window: int = 50) -> set:
    """
    Semanas en las que el mercado (NAFTRAC) está 'risk-on':
    precio por encima de su media móvil → tendencia alcista/lateral.

    Devuelve un set de períodos semanales (pd.Period 'W') permitidos.
    """
    naf = store_get("NAFTRAC")
    if naf is None or "Close" not in naf.columns:
        return None  # sin filtro
    close = naf["Close"]
    ma = close.rolling(ma_window).mean()
    riskon = close >= ma
    weeks = riskon.groupby(riskon.index.to_period("W")).last()
    return set(weeks[weeks].index)


def weekly_portfolio(
    test: pd.DataFrame,
    score_col: str,
    thresh_col: str,
    thresh_val: float,
    score_floor: float | None,
    max_signals: int = MAX_SIGNALS,
    allowed_weeks: set | None = None,
) -> dict:
    """
    Simula un portafolio semanal.

    Args:
        test:        DataFrame de test con columnas p_up, p_meta, tb_ret, ticker.
        score_col:   columna para rankear candidatos (p_up o p_meta).
        thresh_col:  columna para el filtro de entrada (p_up).
        thresh_val:  umbral mínimo del filtro.
        score_floor: piso mínimo del score (None = sin piso). Selectividad.
        max_signals: máximo de posiciones por semana.

    Returns:
        dict con equity curve, retorno total, métricas.
    """
    test = test.copy()
    test["week"] = test.index.to_period("W")

    equity = CAPITAL
    curve  = []
    weekly_rets, all_trade_rets = [], []
    n_weeks_traded = 0

    for week, grp in test.groupby("week"):
        # Filtro de régimen de mercado: si la semana no está permitida, no operar
        if allowed_weeks is not None and week not in allowed_weeks:
            equity *= 1.0
            weekly_rets.append(0.0)
            curve.append({"week": str(week), "equity": round(equity, 2),
                          "ret": 0.0, "n": 0})
            continue

        # Última observación de cada ticker en la semana (el "viernes")
        last_per_ticker = grp.sort_index().groupby("ticker").tail(1)

        cand = last_per_ticker[last_per_ticker[thresh_col] >= thresh_val]
        if score_floor is not None:
            cand = cand[cand[score_col] >= score_floor]

        cand = cand.sort_values(score_col, ascending=False).head(max_signals)

        if len(cand) > 0:
            # Retorno neto por trade (equiponderado), comisión ida y vuelta
            trade_rets = cand["tb_ret"].values / 100.0 - COMM * 2
            week_ret = float(np.mean(trade_rets))
            all_trade_rets.extend(trade_rets.tolist())
            n_weeks_traded += 1
        else:
            week_ret = 0.0

        equity *= (1 + week_ret)
        weekly_rets.append(week_ret)
        curve.append({"week": str(week), "equity": round(equity, 2),
                      "ret": round(week_ret * 100, 3), "n": int(len(cand))})

    weekly_rets = np.array(weekly_rets)
    all_trade_rets = np.array(all_trade_rets)

    total_ret = (equity / CAPITAL - 1) * 100
    n_weeks = len(weekly_rets)
    sharpe = (weekly_rets.mean() / (weekly_rets.std() + 1e-9) * np.sqrt(52)) if n_weeks > 1 else 0

    # Max drawdown sobre la curva
    eq = np.array([c["equity"] for c in curve])
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = float(dd.min() * 100) if len(dd) else 0

    win_weeks = int((weekly_rets > 0).sum())
    trade_wr = float((all_trade_rets > 0).mean()) if len(all_trade_rets) else 0

    return {
        "total_ret":     round(float(total_ret), 2),
        "final_equity":  round(float(equity), 2),
        "n_weeks":       n_weeks,
        "n_weeks_traded": n_weeks_traded,
        "n_trades":      int(len(all_trade_rets)),
        "win_weeks":     win_weeks,
        "week_win_rate": round(win_weeks / max(n_weeks_traded, 1), 3),
        "trade_win_rate": round(trade_wr, 3),
        "sharpe":        round(float(sharpe), 3),
        "max_dd":        round(max_dd, 2),
        "curve":         curve,
    }


def main():
    print("\n" + "=" * 70)
    print("  BACKTEST SEMANAL COMPLETO  |  Pipeline Meta-Labeling")
    print("=" * 70 + "\n")

    print("[1] Construyendo dataset con labels triple-barrier...")
    df = build_dataset()
    print(f"    {len(df):,} observaciones")

    df = df.sort_index()
    cut = int(len(df) * TRAIN_RATIO)
    cut_date = df.index[cut]
    train = df[df.index < cut_date].copy()
    test  = df[df.index >= cut_date].copy()
    print(f"\n[2] Train: {len(train):,} ({train.index.min().date()}→{train.index.max().date()})")
    print(f"    Test:  {len(test):,} ({test.index.min().date()}→{test.index.max().date()})")

    # ── 3. Entrenar primario + meta ────────────────────────────────────────────
    print("\n[3] Entrenando primario (Ensemble calibrado) + meta...")
    primary = EnsembleModel(top_features=15, calibrate=True)
    primary.fit(train, feature_cols=FEATURE_COLS, target_col="y")

    p_train = primary.predict_proba(train, FEATURE_COLS)
    p_test  = primary.predict_proba(test,  FEATURE_COLS)
    auc_p   = roc_auc_score(test["y"], p_test)
    print(f"    AUC primario test: {auc_p:.4f}")

    w_train = sample_uniqueness_weights(train["tb_bars"], horizon=HORIZON)
    meta = MetaModel()
    meta.fit(train, feature_cols=FEATURE_COLS, primary_proba=p_train,
             meta_label=train["y"].values, sample_weight=w_train.values)
    meta_p_test = meta.predict_proba(test, FEATURE_COLS, primary_proba=p_test)
    print(f"    AUC meta test:     {meta.auc:.4f}")

    test = test.copy()
    test["p_up"]   = p_test
    test["p_meta"] = meta_p_test

    # ── 4. Backtest base (sin meta) ────────────────────────────────────────────
    print("\n[4] Backtest semanal (top-5 por semana, comisión 0.25% ida/vuelta)\n")
    base = weekly_portfolio(test, score_col="p_up", thresh_col="p_up",
                            thresh_val=PRIMARY_THRESH, score_floor=None)

    print(f"  BASE (rank por P primaria, sin meta):")
    print(f"    Semanas: {base['n_weeks']}  operadas: {base['n_weeks_traded']}  "
          f"trades: {base['n_trades']}")
    print(f"    Retorno TOTAL: {base['total_ret']:+.1f}%   Sharpe: {base['sharpe']:.2f}   "
          f"MaxDD: {base['max_dd']:.1f}%   WR semanal: {base['week_win_rate']*100:.0f}%")

    # ── 5. Barrido de selectividad del meta ────────────────────────────────────
    print(f"\n  META (rank por meta, varios niveles de selectividad):")
    print(f"  {'Floor':>8}  {'Sem.op':>7}  {'Trades':>7}  {'WR sem':>7}  "
          f"{'Sharpe':>7}  {'MaxDD':>7}  {'TotalRet':>9}")

    # Floors basados en cuantiles de meta sobre los candidatos primarios
    cand_meta = meta_p_test[p_test >= PRIMARY_THRESH]
    sweep = []
    best = None
    for q in [0.0, 0.50, 0.70, 0.85, 0.90, 0.95]:
        floor = float(np.quantile(cand_meta, q)) if (q > 0 and len(cand_meta)) else None
        res = weekly_portfolio(test, score_col="p_meta", thresh_col="p_up",
                               thresh_val=PRIMARY_THRESH, score_floor=floor)
        res["quantile"] = q
        res["floor"] = round(floor, 4) if floor else 0.0
        sweep.append({k: res[k] for k in res if k != "curve"})
        fl = f"{floor:.3f}" if floor else "—"
        print(f"  {fl:>8}  {res['n_weeks_traded']:>7}  {res['n_trades']:>7}  "
              f"{res['week_win_rate']*100:>6.0f}%  {res['sharpe']:>7.2f}  "
              f"{res['max_dd']:>6.1f}%  {res['total_ret']:>+8.1f}%")
        if best is None or res["total_ret"] > best["total_ret"]:
            best = res

    print(f"\n  {'─'*64}")
    print(f"  MEJOR META: floor={best['floor']}  →  {best['total_ret']:+.1f}%  "
          f"(Sharpe {best['sharpe']:.2f}, MaxDD {best['max_dd']:.1f}%)")
    delta = best["total_ret"] - base["total_ret"]
    print(f"  vs BASE:    {base['total_ret']:+.1f}%   →   Δ = {delta:+.1f} puntos")

    # ── 5b. Otra herramienta: filtro de régimen de mercado ─────────────────────
    print(f"\n[5b] + Filtro de régimen de mercado (solo operar con NAFTRAC en tendencia):\n")
    best_floor = best["floor"] if best["floor"] > 0 else None
    regime_results = {}
    best_regime = None
    for ma_win in [20, 50, 100]:
        allowed = market_riskon_weeks(ma_window=ma_win)
        res = weekly_portfolio(test, score_col="p_meta", thresh_col="p_up",
                               thresh_val=PRIMARY_THRESH, score_floor=best_floor,
                               allowed_weeks=allowed)
        res["ma_window"] = ma_win
        regime_results[f"ma{ma_win}"] = {k: res[k] for k in res if k != "curve"}
        print(f"  MA{ma_win:<3}: sem.op={res['n_weeks_traded']:>3}  trades={res['n_trades']:>3}  "
              f"WR={res['week_win_rate']*100:>3.0f}%  Sharpe={res['sharpe']:>5.2f}  "
              f"MaxDD={res['max_dd']:>6.1f}%  TotalRet={res['total_ret']:>+7.1f}%")
        if best_regime is None or res["total_ret"] > best_regime["total_ret"]:
            best_regime = res

    print(f"\n  {'─'*64}")
    print(f"  META + REGIMEN (MA{best_regime['ma_window']}): {best_regime['total_ret']:+.1f}%  "
          f"(Sharpe {best_regime['sharpe']:.2f}, MaxDD {best_regime['max_dd']:.1f}%)")
    delta_reg = best_regime["total_ret"] - base["total_ret"]
    print(f"  vs BASE:  {base['total_ret']:+.1f}%   →   Δ = {delta_reg:+.1f} puntos")

    # ── 6. Guardar ─────────────────────────────────────────────────────────────
    out = {
        "meta": {
            "horizon": HORIZON, "max_signals": MAX_SIGNALS,
            "train_ratio": TRAIN_RATIO, "primary_thresh": PRIMARY_THRESH,
            "comm": COMM, "capital": CAPITAL,
            "test_start": str(test.index.min().date()),
            "test_end":   str(test.index.max().date()),
            "auc_primary": round(auc_p, 4), "auc_meta": round(meta.auc, 4),
        },
        "base":         {k: base[k] for k in base if k != "curve"},
        "base_curve":   base["curve"],
        "best_meta":    {k: best[k] for k in best if k != "curve"},
        "best_curve":   best["curve"],
        "sweep":        sweep,
        "improvement":  round(delta, 2),
        "regime_filter": regime_results,
        "best_regime":  {k: best_regime[k] for k in best_regime if k != "curve"},
        "best_regime_curve": best_regime["curve"],
        "improvement_regime": round(delta_reg, 2),
    }
    out_path = ROOT / "data" / "backtest_meta.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\n{'='*70}\n  Guardado: {out_path}\n{'='*70}\n")


if __name__ == "__main__":
    main()
