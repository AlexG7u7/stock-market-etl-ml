"""Tests for point-in-time news history panel."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.ml.news import Article, _compute_features_from_articles
from src.ml.news_history import merge_news_history


def test_compute_features_asof_no_future_leakage():
    """Artículos posteriores a as_of no deben afectar el score."""
    as_of = datetime(2023, 6, 15, 23, 59, 59, tzinfo=timezone.utc)
    ts_in = int(datetime(2023, 6, 14, 12, 0, tzinfo=timezone.utc).timestamp())
    ts_future = int(datetime(2023, 6, 20, 12, 0, tzinfo=timezone.utc).timestamp())
    arts = [
        Article("WALMEX", "subida record utilidades", "", "u1", ts_in, "gdelt", 0.8),
        Article("WALMEX", "caida fuerte ventas", "", "u2", ts_future, "gdelt", -0.7),
    ]
    feat = _compute_features_from_articles(arts, as_of=as_of, days_back=7)
    assert feat["news_sent_score"] > 0
    assert feat["n_articles"] == 1


def test_merge_news_history_by_date():
    panel = pd.DataFrame({
        "ticker": ["A", "A", "B"],
        "fwd_ret": [1.0, 2.0, 3.0],
    }, index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-02"]))

    daily = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-02"]),
        "ticker": ["A", "A", "B"],
        "news_sent_score": [0.5, -0.2, 0.1],
        "news_count_7d": [1.0, 0.5, 0.3],
        "news_sent_delta": [0.0, 0.0, 0.0],
        "news_sent_vol": [0.0, 0.0, 0.0],
        "news_relevance_avg": [1.0, 1.0, 1.0],
        "news_esg_score": [0.0, 0.0, 0.0],
    })

    out = merge_news_history(panel, daily)
    assert out.loc["2024-01-02", "news_sent_score"].iloc[0] == 0.5
    assert out.loc["2024-01-03", "news_sent_score"] == -0.2
    assert out.loc["2024-01-02", "news_sent_score"].iloc[1] == 0.1
