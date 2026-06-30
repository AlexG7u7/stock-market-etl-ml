"""Tests for super_metrics uncertainty helpers."""
from __future__ import annotations

import numpy as np

from src.ml.super_metrics import (
    CORE_MODELS,
    bootstrap_auc_ci,
    compute_ticker_metrics,
    build_model_registry,
)


def test_bootstrap_auc_ci_bounds():
    rng = np.random.default_rng(0)
    n = 400
    y = rng.integers(0, 2, n)
    p = rng.random(n)
    ci = bootstrap_auc_ci(y, p, n_boot=50)
    assert ci["ci_low"] <= ci["auc"] <= ci["ci_high"]
    assert ci["n"] == n


def test_core_models_count():
    assert len(CORE_MODELS) == 4


def test_ticker_metrics_has_conviction_ci():
    m = compute_ticker_metrics(
        signals={"xs_lgbm": 0.6, "ensemble": 0.58, "heuristic": 0.55},
        conviction_raw=0.59,
        conviction_adj=0.59,
        disagreement=0.04,
        model_weights={"xs_lgbm": 0.4, "ensemble": 0.35, "heuristic": 0.25},
        model_metrics={},
        regime_info={"estado": "lateral", "proba": {"bull": 0.3, "lateral": 0.5, "bear": 0.2}},
        rank_global=3,
        n_universe=19,
    )
    assert "ci_90" in m["conviction"]
    assert m["consensus"]["n_bullish"] >= 2


def test_model_registry():
    reg = build_model_registry({"xs_lgbm", "ensemble", "heuristic"})
    assert reg["n_core"] == 4
    assert sum(1 for m in reg["core_models"] if m["active"]) == 3
