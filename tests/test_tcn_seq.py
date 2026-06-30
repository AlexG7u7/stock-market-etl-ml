"""Tests TCN-LSTM secuencial (KB-070)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.lstm_seq import add_target_up, build_sliding_sequences
from src.ml.shared.models.tcn_model import TF_AVAILABLE
from src.ml.tcn_seq import TCNSeqPredictor


def _panel(n_days: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    close = 100 + np.cumsum(rng.normal(0, 1, n_days))
    df = pd.DataFrame(
        {"Open": close * 0.99, "Close": close,
         "feat_a": rng.normal(0, 1, n_days), "feat_b": rng.normal(0, 1, n_days),
         "ticker": "TK0"},
        index=dates,
    )
    return add_target_up(df, use_cross_section=False)


@pytest.mark.skipif(not TF_AVAILABLE, reason="TensorFlow no instalado")
def test_tcn_fit_and_evaluate():
    df = _panel()
    pred = TCNSeqPredictor(sequence_length=15, epochs=3, filters=16, lstm_units=16)
    metrics = pred.fit(df, ["feat_a", "feat_b"])
    assert pred.is_fitted
    assert metrics["n_samples"] > 0
    auc = pred.evaluate_auc(df, ["feat_a", "feat_b"])
    assert 0.0 <= auc <= 1.0


def test_tcn_reuses_sliding_sequences():
    df = _panel(n_days=80)
    X, y, _, _ = build_sliding_sequences(df, ["feat_a", "feat_b"], "target_up", 10)
    assert X.shape[0] == len(y) > 0
