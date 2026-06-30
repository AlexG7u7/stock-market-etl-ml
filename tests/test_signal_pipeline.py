"""Tests for unified signal pipeline helpers."""
from __future__ import annotations

from src.ml.bet_policy import filter_actionable_ranking
from src.ml.signal_pipeline import bmv_ranking, gemini_size_factor


def test_gemini_size_factor():
    assert gemini_size_factor({"veredicto": "CONFIRMA"}) == 1.0
    assert gemini_size_factor({"veredicto": "DEGRADA"}) == 0.5
    assert gemini_size_factor({"veredicto": "VETA"}) == 0.0
    assert gemini_size_factor(None) == 0.75


def test_bmv_ranking_filters_and_sorts():
    ranking = [
        {"ticker": "A", "universe_slug": "usa", "conviction": 0.9},
        {"ticker": "B", "universe_slug": "bmv", "conviction": 0.7},
        {"ticker": "C", "universe_slug": "bmv", "conviction": 0.8},
    ]
    bmv = bmv_ranking(ranking)
    assert [x["ticker"] for x in bmv] == ["C", "B"]


def test_filter_actionable_respects_gemini_veto():
    ranking = [
        {"ticker": "A", "conviction": 0.6, "gemini": {"veredicto": "VETA"}},
        {"ticker": "B", "conviction": 0.58, "gemini": {"veredicto": "CONFIRMA"}},
    ]
    out = filter_actionable_ranking(ranking, max_signals=2)
    assert len(out) == 1
    assert out[0]["ticker"] == "B"
