"""Tests for KB literature modulators (kb_enhance.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.ml.kb_enhance import (
    apply_kb_modulators,
    get_wti_ret5_pct,
    load_horizon_consensus,
    select_priority_features,
    select_priority_rn_cols,
)


def test_select_priority_features_respects_kumbure_order():
    avail = ["z_custom", "ret_5d", "rsi_14", "foo"]
    out = select_priority_features(avail, include_news=False, max_cols=10)
    assert out[0] == "ret_5d"
    assert out[1] == "rsi_14"
    assert "z_custom" in out


def test_select_priority_rn_cols():
    rn = ["rn_foo", "rn_ret_5d", "rn_rsi_14", "rn_bar"]
    out = select_priority_rn_cols(rn, max_cols=10)
    assert out[0] == "rn_ret_5d"
    assert out[1] == "rn_rsi_14"


def test_horizon_consensus_boost():
    conv, flags, meta = apply_kb_modulators(
        ticker="ALSEA",
        universe_slug="bmv",
        conviction=0.60,
        disagreement=0.10,
        signals={"xs_lgbm": 0.62, "ensemble": 0.58},
        news_sent=0.1,
        n_horizontes=4,
    )
    assert conv > 0.60
    assert any("LR-012" in f for f in flags)
    assert "LR-012" in meta["rules_applied"]


def test_wti_energy_penalty():
    conv, flags, _ = apply_kb_modulators(
        ticker="VISTA",
        universe_slug="bmv",
        conviction=0.65,
        disagreement=0.08,
        signals={"xs_lgbm": 0.7, "ensemble": 0.68},
        news_sent=0.0,
        wti_ret5_pct=-5.0,
    )
    assert conv < 0.65
    assert any("LR-011" in f for f in flags)


def test_news_contradiction_penalty():
    conv, flags, _ = apply_kb_modulators(
        ticker="WALMEX",
        universe_slug="bmv",
        conviction=0.62,
        disagreement=0.05,
        signals={"xs_lgbm": 0.65, "ensemble": 0.63},
        news_sent=-0.35,
    )
    assert conv < 0.62
    assert any("LR-003" in f for f in flags)


def test_model_direction_disagree():
    conv, flags, _ = apply_kb_modulators(
        ticker="X",
        universe_slug="bmv",
        conviction=0.58,
        disagreement=0.05,
        signals={"xs_lgbm": 0.62, "ensemble": 0.42},
        news_sent=0.0,
    )
    assert conv < 0.58
    assert any("LR-001" in f for f in flags)


def test_load_horizon_consensus_from_signals(tmp_path: Path):
    payload = {
        "consensus": [
            {"ticker": "ALSEA", "n_horizontes": 3},
            {"ticker": "WALMEX", "n_horizontes": 2},
        ]
    }
    (tmp_path / "bmv.json").write_text(json.dumps(payload))
    out = load_horizon_consensus(tmp_path)
    assert out["ALSEA"] == 3
    assert out["WALMEX"] == 2


def test_get_wti_ret5_pct():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    wti = pd.DataFrame({"Close": [70 + i for i in range(10)]}, index=idx)
    ret = get_wti_ret5_pct({"WTI": wti})
    assert ret is not None
    assert ret > 0
