"""KB-041 — deduplicación TF-IDF de titulares."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from src.ml.news import Article, _compute_features_from_articles


def _make_article(title: str, sentiment: float, ts: int, ticker: str = "TEST") -> Article:
    return Article(
        ticker=ticker,
        title=title,
        summary="",
        url=f"https://example.com/{hash(title)}",
        published_ts=ts,
        source="test",
        sentiment=sentiment,
    )


@pytest.fixture
def now_ts() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def test_three_identical_headlines_sentiment_not_tripled(now_ts: int) -> None:
    """3 titulares idénticos no deben triplicar el peso efectivo en agregación."""
    title = "Alsea reporta ganancias récord en trimestre"
    articles = [
        _make_article(title, 1.0, now_ts),
        _make_article(title, 1.0, now_ts),
        _make_article(title, 1.0, now_ts),
    ]

    with_dedup = _compute_features_from_articles(
        [a for a in articles],
        days_back=7,
        lambda_decay=0.0,
        apply_dedup=True,
    )
    without_dedup = _compute_features_from_articles(
        [a for a in articles],
        days_back=7,
        lambda_decay=0.0,
        apply_dedup=False,
    )

    # Sentimiento idéntico, pero conteo efectivo (news_count_7d) menor con dedup
    assert with_dedup["news_sent_score"] == pytest.approx(1.0)
    assert with_dedup["news_count_7d"] < without_dedup["news_count_7d"]
    # Pesos dedup: 1 + 0.5 + 0.25 = 1.75 vs 3 sin dedup → log(2.75) vs log(4)
    assert with_dedup["news_count_7d"] == pytest.approx(float(np.log1p(1.75)), rel=1e-3)
