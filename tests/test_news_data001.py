"""DATA-001 — neutral sentiment sin artículos; Gemini batch solo en ventana."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.ml.news import (
    Article,
    _compute_features_from_articles,
    _neutral_news_features,
    batch_score_gemini,
)
from src.ml.news_sources import compute_relevance_score


def _ts_days_ago(days: float) -> int:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return int(dt.timestamp())


def test_neutral_features_all_zero() -> None:
    feat = _neutral_news_features()
    assert feat["news_sent_score"] == 0.0
    assert feat["news_count_7d"] == 0.0
    assert feat["n_articles"] == 0


def test_gemini_batch_ignores_out_of_window_headlines() -> None:
    old = Article(
        ticker="CEMEX",
        title="Cemex reporta resultados",
        summary="",
        url="http://x.com/1",
        published_ts=_ts_days_ago(30),
        source="test",
    )
    scores = batch_score_gemini({"CEMEX": [old]}, days_back=7)
    assert scores == {}


def test_no_gemini_override_when_n_articles_zero() -> None:
    """Simula batch: artículo viejo → n_articles=0 → neutral."""
    old = Article(
        ticker="X",
        title="Titular viejo",
        summary="",
        url="http://x.com/2",
        published_ts=_ts_days_ago(20),
        source="test",
        sentiment=0.9,
    )
    feat = _compute_features_from_articles([old], days_back=7, lambda_decay=0.0)
    assert feat["n_articles"] == 0
    if feat["n_articles"] == 0:
        feat = _neutral_news_features()
    assert feat["news_sent_score"] == 0.0


def test_indexity_relevance_matches_ticker() -> None:
    score = compute_relevance_score(
        "Indexity - OMA - Cumplimiento de su ODS",
        "",
        ["OMA", "OMAB", "aeropuertos"],
    )
    assert score >= 1.0
