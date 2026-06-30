"""Tests for relevance weighting, ESG features, AV sentiment, and dedup."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest

from src.ml.news import (
    Article,
    LOW_RELEVANCE_THRESHOLD,
    LOW_RELEVANCE_WEIGHT,
    NEWS_FEATURE_COLS,
    _compute_features_from_articles,
    score_with_gemini,
)
from src.ml.news_sources import compute_relevance_score, is_esg_headline


def _ts_now() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _make_article(
    title: str,
    sentiment: float,
    *,
    relevance: float = 1.0,
    av_sentiment: float | None = None,
    ts: int | None = None,
) -> Article:
    return Article(
        ticker="ALSEA",
        title=title,
        summary="",
        url=f"https://example.com/{hash(title)}",
        published_ts=ts or _ts_now(),
        source="test",
        sentiment=sentiment,
        relevance_score=relevance,
        av_sentiment=av_sentiment,
    )


def test_news_feature_cols_includes_new_columns() -> None:
    assert "news_relevance_avg" in NEWS_FEATURE_COLS
    assert "news_esg_score" in NEWS_FEATURE_COLS


def test_low_relevance_reduces_effective_weight() -> None:
    """Low-relevance articles contribute less to news_count_7d."""
    high_rel = _make_article("Alsea gana en BMV", 1.0, relevance=0.9)
    low_rel = _make_article("IPC sube en mercado", 1.0, relevance=0.1)

    feat_high = _compute_features_from_articles([high_rel], days_back=7, lambda_decay=0.0)
    feat_low = _compute_features_from_articles([low_rel], days_back=7, lambda_decay=0.0)

    assert feat_low["news_count_7d"] < feat_high["news_count_7d"]
    assert feat_low["news_relevance_avg"] < feat_high["news_relevance_avg"]


def test_esg_score_from_esg_headlines_only() -> None:
    esg = _make_article("Alsea avanza en sostenibilidad y emisiones", 0.8, relevance=1.0)
    regular = _make_article("Alsea reporta ventas", -0.5, relevance=1.0)

    feat = _compute_features_from_articles(
        [esg, regular], days_back=7, lambda_decay=0.0, apply_dedup=False,
    )

    assert is_esg_headline(esg.title)
    assert feat["news_esg_score"] == pytest.approx(0.8)
    assert feat["news_sent_score"] != feat["news_esg_score"]


def test_alpha_vantage_sentiment_overrides_keywords() -> None:
    art = _make_article("Neutral headline", 0.0, av_sentiment=0.65)
    with patch.dict("os.environ", {}, clear=True):
        scored = score_with_gemini([art], "TestCo")
    assert scored[0].sentiment == pytest.approx(0.65)


def test_gemini_default_on_with_api_key() -> None:
    art = _make_article("Alsea sube", 0.0)
    env = {"GEMINI_API_KEY": "test-key"}
    with patch.dict("os.environ", env, clear=True):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_resp = mock_client.models.generate_content.return_value
            mock_resp.text = '{"1": 0.5}'
            scored = score_with_gemini([art], "Alsea")
    assert scored[0].sentiment == pytest.approx(0.5)
    mock_client_cls.assert_called_once()


def test_gemini_opt_out_with_false_flag() -> None:
    art = _make_article("Alsea sube", 0.0, av_sentiment=0.3)
    env = {"GEMINI_API_KEY": "test-key", "GEMINI_NEWS_ENABLED": "false"}
    with patch.dict("os.environ", env, clear=True):
        with patch("google.genai.Client") as mock_client_cls:
            scored = score_with_gemini([art], "Alsea")
    assert scored[0].sentiment == pytest.approx(0.3)
    mock_client_cls.assert_not_called()


def test_dedup_still_works_with_relevance_weights() -> None:
    """KB-041 dedup must still down-weight duplicate headlines."""
    title = "Alsea reporta ganancias récord en trimestre"
    articles = [
        _make_article(title, 1.0, relevance=1.0),
        _make_article(title, 1.0, relevance=1.0),
        _make_article(title, 1.0, relevance=1.0),
    ]

    with_dedup = _compute_features_from_articles(
        [a for a in articles], days_back=7, lambda_decay=0.0, apply_dedup=True,
    )
    without_dedup = _compute_features_from_articles(
        [a for a in articles], days_back=7, lambda_decay=0.0, apply_dedup=False,
    )

    assert with_dedup["news_sent_score"] == pytest.approx(1.0)
    assert with_dedup["news_count_7d"] < without_dedup["news_count_7d"]
    assert with_dedup["news_count_7d"] == pytest.approx(float(np.log1p(1.75)), rel=1e-3)


def test_compute_relevance_score_exported_consistency() -> None:
    score = compute_relevance_score("Walmex abre tiendas", "", ["Walmex", "WALMEX"])
    assert score == 1.0
    assert LOW_RELEVANCE_THRESHOLD == 0.4
    assert LOW_RELEVANCE_WEIGHT == 0.3
