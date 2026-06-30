"""
Tres experimentos P0 — validación de edge neto.

  1. News A/B      — AUC walk-forward con/sin NEWS_FEATURE_COLS
  2. Stacking A/B  — meta-LR vs AUC-weight → AUC + Sharpe neto top-K
  3. Grid umbrales — K × min P(up) buscando Sharpe neto > 0

Exporta: data/eval/experiments.json (y merge en dashboard_eval.json)

Uso:
    ./venv/bin/python scripts/run_experiments.py
    ./venv/bin/python scripts/run_experiments.py --skip-news-fetch
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from scripts.backtest_topk import (
    TRAIN_RATIO,
    build_panel,
    load_universe_tickers,
    run_topk_backtest,
)
from src.ml.ensemble import EnsembleModel
from src.ml.features import (
    FEATURE_COLS,
    NEWS_FEATURE_COLS,
    add_news_features,
    compute_signal_score,
    get_all_feature_cols,
)
from src.ml.shared.evaluators.metrics import Metrics

EVAL_DIR = ROOT / "data" / "eval"
OUT_PATH = EVAL_DIR / "experiments.json"


def _safe_auc(y: np.ndarray, p: np.ndarray) -> float:
    if len(y) < 2 or len(np.unique(y)) < 2:
        return 0.5
    return float(roc_auc_score(y, p))


def _split_panel(universe: str = "bmv") -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = load_universe_tickers(universe)
    df = build_panel(tickers).sort_index()
    cut = df.index[int(len(df) * TRAIN_RATIO)]
    train = df[df.index < cut].copy()
    test = df[df.index >= cut].copy()
    return train, test


def _load_news_df(tickers: dict[str, str], skip_fetch: bool) -> pd.DataFrame | None:
    from src.ml.news import batch_news_features, load_cached_news_features

    cached = load_cached_news_features()
    if cached is not None and not cached.empty:
        return cached.reset_index() if "ticker" not in cached.columns else cached

    if skip_fetch:
        return None

    print("  Fetching news (cache vacío)…")
    try:
        return batch_news_features(tickers, days_back=7, verbose=False, save_cache=True)
    except Exception as exc:
        print(f"  News fetch failed: {exc}")
        return None


def _merge_news_panel(df: pd.DataFrame, news_df: pd.DataFrame | None) -> pd.DataFrame:
    if news_df is None or news_df.empty:
        out = df.copy()
        for col in NEWS_FEATURE_COLS:
            out[col] = 0.0
        return out
    return add_news_features(df, news_df)


def _add_fusion_cols(df: pd.DataFrame, feat_cols: list[str]) -> pd.DataFrame:
    """Rank-normalize + pct_fwd para stacking (como SuperModel)."""
    out = df.copy()
    g = out.groupby(out.index)
    for c in feat_cols:
        if c in out.columns:
            out[f"rn_{c}"] = g[c].rank(pct=True)
    out["pct_fwd"] = g["fwd_ret"].rank(pct=True)
    if "signal_score" not in out.columns:
        scores = out.apply(compute_signal_score, axis=1)
        out["signal_score"] = scores.apply(lambda x: x[0])
    sig_g = out.groupby(out.index)["signal_score"]
    out["rn_signal"] = sig_g.rank(pct=True)
    return out


def _fit_ensemble_probs(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feat_cols: list[str],
    target_col: str = "y_rel",
) -> tuple[np.ndarray, np.ndarray, float]:
    model = EnsembleModel(top_features=min(15, len(feat_cols)), calibrate=True)
    use_cols = [c for c in feat_cols if c in train.columns]
    model.fit(train, feature_cols=use_cols, target_col=target_col)
    p_tr = model.predict_proba(train, use_cols)
    p_te = model.predict_proba(test, use_cols)
    auc = _safe_auc(test[target_col].values, p_te)
    return p_tr, p_te, auc


def _merge_news_panel_historical(df: pd.DataFrame) -> pd.DataFrame:
    from src.ml.news_history import load_daily_features, merge_news_history

    return merge_news_history(df, load_daily_features())


def experiment_news_ab(
    train: pd.DataFrame,
    test: pd.DataFrame,
    tickers: dict[str, str],
    skip_fetch: bool,
    *,
    use_historical: bool = True,
) -> dict:
    print("\n══ EXP 1 — News A/B (AUC OOS y_rel) ══")
    print(f"  Modo merge: {'historical PIT' if use_historical else 'snapshot (legacy)'}")

    _, p_base, auc_base = _fit_ensemble_probs(train, test, FEATURE_COLS)
    news_ok = False
    n_with = 0
    p_news = p_base
    auc_news = auc_base

    if use_historical:
        from src.ml.news_history import history_stats, load_daily_features

        daily = load_daily_features()
        stats = history_stats()
        if daily is None or daily.empty:
            print("  ⚠ Sin panel histórico — corre: python scripts/build_news_history.py")
        else:
            news_ok = True
            print(f"  Panel: {stats.get('rows', 0):,} filas, "
                  f"{stats.get('date_min')} → {stats.get('date_max')}, "
                  f"{stats.get('pct_nonzero_sent', 0)}% sent≠0")
            train_n = _merge_news_panel_historical(train)
            test_n = _merge_news_panel_historical(test)
            n_with = int((test_n["news_sent_score"].abs() > 1e-6).sum())
            feat_news = get_all_feature_cols(include_news=True)
            _, p_news, auc_news = _fit_ensemble_probs(train_n, test_n, feat_news)
    else:
        news_df = _load_news_df(tickers, skip_fetch)
        news_ok = news_df is not None and not news_df.empty
        if news_ok:
            train_n = _merge_news_panel(train, news_df)
            test_n = _merge_news_panel(test, news_df)
            n_with = int((test_n["news_sent_score"].abs() > 1e-6).sum())
            feat_news = get_all_feature_cols(include_news=True)
            _, p_news, auc_news = _fit_ensemble_probs(train_n, test_n, feat_news)

    delta = round(auc_news - auc_base, 4)
    pred_diff = float(np.abs(p_base - p_news).mean()) if len(p_base) else 0.0

    result = {
        "mode": "historical_pit" if use_historical else "snapshot",
        "news_cache_available": news_ok,
        "test_rows_with_news_score": n_with,
        "baseline_auc": round(auc_base, 4),
        "with_news_auc": round(auc_news, 4),
        "delta_auc": delta,
        "mean_pred_diff": round(pred_diff, 6),
        "pass_delta_ge_0.01": delta >= 0.01,
        "feature_cols_baseline": len(FEATURE_COLS),
        "feature_cols_with_news": len(get_all_feature_cols(include_news=True)),
    }
    print(f"  Baseline AUC: {auc_base:.4f}  |  +News: {auc_news:.4f}  |  Δ={delta:+.4f}  "
          f"| Δpred={pred_diff:.4f}")
    return result


def experiment_stacking_ab(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    print("\n══ EXP 2 — Stacking LR vs AUC-weight ══")
    feat = [c for c in FEATURE_COLS if c in train.columns]
    tr = _add_fusion_cols(train, feat)
    te = _add_fusion_cols(test, feat)
    rn = [f"rn_{c}" for c in feat if f"rn_{c}" in tr.columns]
    target = "y_rel"

    # Base: ensemble
    ens = EnsembleModel(top_features=min(15, len(feat)), calibrate=True)
    ens.fit(tr, feature_cols=feat, target_col=target)
    p_ens_tr = ens.predict_proba(tr, feat)
    p_ens_te = ens.predict_proba(te, feat)

    # Base: xs_lgbm proxy
    p_xs_tr = np.full(len(tr), 0.5)
    p_xs_te = np.full(len(te), 0.5)
    try:
        import lightgbm as lgb

        reg = lgb.LGBMRegressor(
            n_estimators=200, num_leaves=31, learning_rate=0.05,
            n_jobs=2, random_state=42, verbosity=-1,
        )
        reg.fit(tr[rn].values, tr["pct_fwd"].values)
        p_xs_tr = reg.predict(tr[rn].values)
        p_xs_te = reg.predict(te[rn].values)
    except Exception as exc:
        print(f"  xs_lgbm skip: {exc}")

    # Base: heuristic
    p_heu_tr = tr["rn_signal"].values.astype(float)
    p_heu_te = te["rn_signal"].values.astype(float)

    # Holdout temporal 20% del train para meta
    dates = tr.index.unique().sort_values()
    cut_i = int(len(dates) * 0.8)
    cut_dt = dates[cut_i]
    meta_mask = np.asarray(tr.index >= cut_dt)
    fit_mask = ~meta_mask

    bases = {
        "ensemble": (p_ens_tr, p_ens_te),
        "xs_lgbm": (p_xs_tr, p_xs_te),
        "heuristic": (p_heu_tr, p_heu_te),
    }

    y_meta = tr.loc[meta_mask, target].values
    X_meta = np.column_stack([bases[m][0][meta_mask] for m in bases])
    mask = np.all(np.isfinite(X_meta), axis=1)
    X_meta, y_meta = X_meta[mask], y_meta[mask]

    # AUC-weight on meta
    aucs = {}
    y_meta_full = tr.loc[meta_mask, target].values
    for name, (ptr, _) in bases.items():
        p_slice = ptr[meta_mask][mask]
        aucs[name] = max(_safe_auc(y_meta, p_slice) - 0.5, 0.0)
    wsum = sum(aucs.values()) or 1.0
    weights = {k: v / wsum for k, v in aucs.items()}
    blend_meta = sum(weights[m] * bases[m][0][meta_mask][mask] for m in bases)
    auc_blend_meta = _safe_auc(y_meta, blend_meta)

    # Stacking LR on meta
    stack_auc_meta = 0.5
    meta_lr = None
    if len(y_meta) >= 50 and len(np.unique(y_meta)) >= 2:
        meta_lr = LogisticRegression(max_iter=500, random_state=42)
        meta_lr.fit(X_meta, y_meta)
        stack_auc_meta = _safe_auc(y_meta, meta_lr.predict_proba(X_meta)[:, 1])

    use_stack = stack_auc_meta >= auc_blend_meta
    print(f"  Meta AUC: stacking={stack_auc_meta:.4f} vs auc-weight={auc_blend_meta:.4f} → "
          f"{'stacking' if use_stack else 'auc-weight'}")

    # Predicciones test completas (re-fit bases on full train)
    X_te = np.column_stack([bases[m][1] for m in bases])
    if use_stack and meta_lr is not None:
        p_fusion = meta_lr.predict_proba(X_te)[:, 1]
        fusion_mode = "stacking"
    else:
        p_fusion = sum(weights[m] * bases[m][1] for m in bases)
        fusion_mode = "auc_weight"

    p_auc_only = sum(weights[m] * bases[m][1] for m in bases)
    auc_stack_test = _safe_auc(te[target].values, p_fusion)
    auc_weight_test = _safe_auc(te[target].values, p_auc_only)

    te_stack = te.copy()
    te_stack["p_up"] = p_fusion
    te_stack["p_rel"] = p_fusion
    te_weight = te.copy()
    te_weight["p_up"] = p_auc_only
    te_weight["p_rel"] = p_auc_only

    bt_stack = run_topk_backtest(te_stack, top_k=5, score_mode="p_up", min_p_up=0.0)
    bt_weight = run_topk_backtest(te_weight, top_k=5, score_mode="p_up", min_p_up=0.0)

    sharpe_stack = bt_stack["strategy"]["sharpe_net"]
    sharpe_weight = bt_weight["strategy"]["sharpe_net"]
    winner = "stacking" if sharpe_stack > sharpe_weight else "auc_weight"

    result = {
        "meta_auc_stacking": round(stack_auc_meta, 4),
        "meta_auc_weight": round(auc_blend_meta, 4),
        "test_auc_stacking": round(auc_stack_test, 4),
        "test_auc_weight": round(auc_weight_test, 4),
        "fusion_selected": fusion_mode,
        "sharpe_net_stacking": round(sharpe_stack, 3),
        "sharpe_net_auc_weight": round(sharpe_weight, 3),
        "winner_sharpe": winner,
        "pass_sharpe_improvement": bool(sharpe_stack > sharpe_weight),
    }
    print(f"  Sharpe neto: stacking={sharpe_stack:.3f} vs auc-weight={sharpe_weight:.3f} → {winner}")
    return result


def experiment_threshold_grid(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> dict:
    print("\n══ EXP 3 — Grid K × umbral P(up) ══")
    _, p_te, _ = _fit_ensemble_probs(train, test, FEATURE_COLS)
    test = test.copy()
    test["p_up"] = p_te
    test["p_rel"] = p_te

    grid_k = [2, 3, 5]
    grid_thresh = [0.0, 0.53, 0.56, 0.58, 0.60]
    rows: list[dict] = []

    for k in grid_k:
        for thr in grid_thresh:
            if thr == 0.0 and k != 5:
                continue
            bt = run_topk_backtest(
                test, top_k=k, score_mode="p_up",
                weight_mode="equal", min_p_up=thr,
            )
            s = bt["strategy"]
            n_periods = s.get("n_periods", 0)
            rows.append({
                "top_k": k,
                "min_p_up": thr,
                "sharpe_net": round(s["sharpe_net"], 3),
                "sharpe_gross": round(s["sharpe_gross"], 3),
                "total_return_net_pct": round(s["total_return_net"] * 100, 2),
                "max_drawdown_pct": round(s["max_drawdown"] * 100, 2),
                "win_rate_net": round(s["win_rate_net"] * 100, 1),
                "n_periods": n_periods,
            })
            print(f"  K={k} thr={thr:.2f} → Sharpe net {s['sharpe_net']:.3f}  "
                  f"ret {s['total_return_net']*100:+.1f}%  periods={n_periods}")

    rows.sort(key=lambda r: r["sharpe_net"], reverse=True)
    robust = [r for r in rows if r["n_periods"] >= 20]
    best = rows[0] if rows else None
    best_robust = max(robust, key=lambda r: r["sharpe_net"]) if robust else None
    any_pos = any(r["sharpe_net"] > 0 for r in robust)

    return {
        "variants": rows,
        "best": best,
        "best_robust_min_20_periods": best_robust,
        "any_sharpe_net_positive": any_pos,
        "low_n_warning": bool(
            best is not None and best.get("n_periods", 0) < 20
            and (best_robust is None or best_robust["sharpe_net"] != best["sharpe_net"])
        ),
        "recommendation": (
            f"K={best_robust['top_k']} min_p={best_robust['min_p_up']} "
            f"Sharpe {best_robust['sharpe_net']} ({best_robust['n_periods']} períodos)"
            if best_robust
            else "Sin config robusta (≥20 períodos) con Sharpe neto > 0"
        ),
    }


def _merge_dashboard(experiments: dict) -> None:
    dash_path = EVAL_DIR / "dashboard_eval.json"
    if dash_path.exists():
        dash = json.loads(dash_path.read_text())
    else:
        dash = {}
    dash["experiments"] = experiments
    dash["experiments_at"] = experiments.get("generated_at")
    dash_path.write_text(json.dumps(dash, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="bmv")
    parser.add_argument("--skip-news-fetch", action="store_true")
    parser.add_argument("--snapshot-news", action="store_true", help="Legacy: usar latest.json")
    args = parser.parse_args()

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_universe_tickers(args.universe)
    train, test = _split_panel(args.universe)

    print(f"\nPanel: train={len(train):,} test={len(test):,} "
          f"({test.index.min().date()} → {test.index.max().date()})")

    exp1 = experiment_news_ab(
        train, test, tickers, args.skip_news_fetch,
        use_historical=not args.snapshot_news,
    )
    exp2 = experiment_stacking_ab(train, test)
    exp3 = experiment_threshold_grid(train, test)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": args.universe,
        "exp1_news_ab": exp1,
        "exp2_stacking_ab": exp2,
        "exp3_threshold_grid": exp3,
        "summary": {
            "news_helps": bool(exp1.get("pass_delta_ge_0.01", False)),
            "stacking_beats_auc_weight": bool(exp2.get("pass_sharpe_improvement", False)),
            "positive_sharpe_found": bool(exp3.get("any_sharpe_net_positive", False)),
            "best_config": exp3.get("best_robust_min_20_periods") or exp3.get("best"),
            "low_n_warning": bool(exp3.get("low_n_warning", False)),
        },
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    _merge_dashboard(out)

    from src.ml.bet_policy import export_policy_json
    export_policy_json()

    print("\n" + "=" * 60)
    print(f"✅ Guardado: {OUT_PATH}")
    print(f"   News ΔAUC≥0.01: {out['summary']['news_helps']}")
    print(f"   Stacking gana Sharpe: {out['summary']['stacking_beats_auc_weight']}")
    print(f"   Sharpe neto > 0: {out['summary']['positive_sharpe_found']}")
    if exp3.get("best_robust_min_20_periods"):
        b = exp3["best_robust_min_20_periods"]
        print(f"   Mejor robusto (≥20p): K={b['top_k']} min_p={b['min_p_up']} → Sharpe {b['sharpe_net']}")
    elif exp3.get("best"):
        b = exp3["best"]
        print(f"   Mejor (⚠️ n={b.get('n_periods')}): K={b['top_k']} min_p={b['min_p_up']} → Sharpe {b['sharpe_net']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
