"""Tests for unified news source fetchers (mocked, no network)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ml.news_sources import (
    compute_relevance_score,
    fetch_alpha_vantage_articles,
    fetch_databursatil_articles,
    fetch_yfinance_articles,
    get_entity_aliases,
    is_esg_headline,
)


class TestRelevanceAndESG:
    def test_compute_relevance_title_match(self) -> None:
        score = compute_relevance_score(
            "Alsea reporta ganancias récord",
            "La cadena de restaurantes creció 10%",
            ["Alsea", "ALSEA"],
        )
        assert score == 1.0

    def test_compute_relevance_summary_only(self) -> None:
        score = compute_relevance_score(
            "Mercado mexicano cierra al alza",
            "Alsea fue una de las emisoras destacadas",
            ["Alsea"],
        )
        assert score == pytest.approx(0.75)

    def test_compute_relevance_unrelated_baseline(self) -> None:
        score = compute_relevance_score(
            "Fed mantiene tasas",
            "Sin mención de empresas",
            ["Alsea"],
        )
        assert score == pytest.approx(0.15)

    def test_is_esg_headline_positive(self) -> None:
        assert is_esg_headline("Empresa lanza plan de sostenibilidad y carbono neto")
        assert is_esg_headline("Reporte ESG destaca gobernanza corporativa")

    def test_is_esg_headline_negative(self) -> None:
        assert not is_esg_headline("Alsea sube 5% en la BMV")


class TestEntityAliases:
    def test_get_entity_aliases_includes_ticker(self) -> None:
        aliases = get_entity_aliases("ALSEA")
        assert "ALSEA" in aliases
        assert "restaurantes" in aliases

    def test_get_entity_aliases_extra_terms(self) -> None:
        aliases = get_entity_aliases("TEST", extra=["CustomCo"])
        assert "CustomCo" in aliases


class TestFetchDatabursatil:
    @patch("src.ml.news_sources.requests.get")
    def test_fetch_databursatil_returns_scored_articles(self, mock_get: MagicMock) -> None:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {
            "top": [
                {"titulo": "ALSEA sube en la BMV", "url": "https://db/1", "fecha": "2026-06-28 10:00:00"},
                {"titulo": "IPC cierra plano", "url": "https://db/2", "fecha": "2026-06-28 09:00:00"},
            ],
        }

        with patch.dict("os.environ", {"DATABURSATIL_API_TOKEN": "tok"}):
            articles = fetch_databursatil_articles("ALSEA", aliases=["ALSEA", "Alsea"], max_items=5)

        assert len(articles) == 1
        assert articles[0]["title"] == "ALSEA sube en la BMV"
        assert articles[0]["source"] == "databursatil"
        assert articles[0]["relevance_score"] == 1.0

    def test_fetch_databursatil_no_token(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert fetch_databursatil_articles("ALSEA") == []


class TestFetchAlphaVantage:
    @patch("src.ml.news_sources.requests.get")
    def test_fetch_alpha_vantage_preserves_sentiment(self, mock_get: MagicMock) -> None:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {
            "feed": [
                {
                    "title": "Apple beats earnings",
                    "summary": "Strong iPhone sales",
                    "url": "https://news/apple",
                    "time_published": "20260628120000",
                    "overall_sentiment_score": "0.42",
                },
            ],
        }

        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "av-key"}):
            articles = fetch_alpha_vantage_articles("AAPL", max_items=3)

        assert len(articles) == 1
        assert articles[0]["av_sentiment"] == pytest.approx(0.42)
        assert articles[0]["source"] == "alpha_vantage"
        assert articles[0]["published_ts"] > 0

    def test_fetch_alpha_vantage_no_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert fetch_alpha_vantage_articles("AAPL") == []


class TestFetchYfinance:
    @patch("src.ml.news_sources.yf.Ticker")
    def test_fetch_yfinance_articles(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.return_value.news = [
            {
                "title": "Walmex expands stores",
                "summary": "Retail growth in Mexico",
                "link": "https://yf/1",
                "providerPublishTime": 1719500000,
            },
        ]

        articles = fetch_yfinance_articles("WALMEX.MX", "WALMEX", max_items=5)
        assert len(articles) == 1
        assert articles[0]["source"] == "yfinance"
        assert articles[0]["relevance_score"] > 0
