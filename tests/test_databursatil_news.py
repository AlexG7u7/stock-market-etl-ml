"""Tests for DataBursátil V2 news client."""
from __future__ import annotations

from src.ml.databursatil_news import (
    _raw_to_article,
    fetch_databursatil_cables_articles,
    fetch_databursatil_noticias_articles,
)


def test_raw_to_article_noticias_fields():
    art = _raw_to_article(
        {"n": "Walmex reporta utilidades", "c": "Detalle...", "f": "https://example.com/x"},
        "WALMEX",
        ["WALMEX", "Walmart"],
    )
    assert art["title"] == "Walmex reporta utilidades"
    assert art["relevance_score"] > 0.3


def test_raw_to_article_cables_t_field():
    art = _raw_to_article(
        {"t": "14:30 Indexity - ALSEA - Resultados trimestrales", "f": "DataBursatil"},
        "ALSEA",
        ["ALSEA", "Alsea"],
    )
    assert "ALSEA" in art["title"] or art["relevance_score"] > 0


def test_fetch_noticias_empty_without_token(monkeypatch):
    monkeypatch.delenv("DATABURSATIL_API_TOKEN", raising=False)
    assert fetch_databursatil_noticias_articles("WALMEX") == []
    assert fetch_databursatil_cables_articles("WALMEX") == []
