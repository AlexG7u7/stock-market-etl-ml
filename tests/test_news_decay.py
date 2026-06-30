"""KB-043 — decay temporal en agregación de sentiment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.ml.news import Article, _compute_features_from_articles


def _make_article(title: str, sentiment: float, days_ago: float, ticker: str = "TEST") -> Article:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return Article(
        ticker=ticker,
        title=title,
        summary="",
        url=f"https://example.com/{title}",
        published_ts=int(dt.timestamp()),
        source="test",
        sentiment=sentiment,
    )


def test_old_news_weighs_less_than_today() -> None:
    """Noticia de hoy (+1) debe dominar sobre noticia vieja (-1) con decay."""
    articles = [
        _make_article("Alsea sube hoy", 1.0, days_ago=0.0),
        _make_article("Alsea cae hace semanas", -1.0, days_ago=10.0),
    ]

    with_decay = _compute_features_from_articles(
        [a for a in articles],
        days_back=14,
        lambda_decay=0.3,
        apply_dedup=False,
    )
    without_decay = _compute_features_from_articles(
        [a for a in articles],
        days_back=14,
        lambda_decay=0.0,
        apply_dedup=False,
    )

    assert with_decay["news_sent_score"] > 0.0
    assert without_decay["news_sent_score"] == pytest.approx(0.0)
    assert with_decay["news_sent_score"] > without_decay["news_sent_score"]
