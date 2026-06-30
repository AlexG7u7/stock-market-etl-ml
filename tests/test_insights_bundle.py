"""Tests for InsightsBundle builder."""
from __future__ import annotations

from src.ml.insights_bundle import (
    build_insights_bundle,
    InsightsBundle,
    _item_to_insight,
)


def _sample_super_result() -> dict:
    return {
        "generated_at": "2026-06-30T12:00:00",
        "n_tickers": 2,
        "model_registry": {"n_core": 4, "core_models": []},
        "universe_metrics": {
            "bmv": {
                "universe": "🇲🇽 Acciones BMV",
                "slug": "bmv",
                "n_tickers": 19,
                "n_scored": 19,
                "fusion": {"selected": "stacking", "stack_auc": 0.52, "auc_weight_auc": 0.51},
                "models": {
                    "ensemble": {
                        "auc": 0.54,
                        "auc_ci_90": [0.48, 0.60],
                        "edge_vs_random": 0.04,
                    },
                },
            },
        },
        "bet_policy": {"paper_only": True, "max_signals": 2},
        "gemini_summary": {"agent": "gemini_trader", "apostar": 1, "modo": "trader"},
        "portfolio_brief": {
            "resumen_ejecutivo": "Semana selectiva BMV.",
            "apostar": ["WALMEX"],
            "esperar": [],
            "evitar": [],
        },
        "master_ranking": [
            {
                "ticker": "WALMEX",
                "universe": "🇲🇽 Acciones BMV",
                "universe_slug": "bmv",
                "rank_global": 1,
                "conviction": 0.61,
                "conviction_raw": 0.58,
                "disagreement": 0.05,
                "signals": {"ensemble": 0.62, "xs_lgbm": 0.59},
                "regime": "lateral",
                "gemini": {
                    "veredicto": "APOSTAR",
                    "como_apostar": {"tamano": "HALF"},
                    "incertidumbres_clave": ["AUC ensemble IC90 incluye 0.50"],
                },
                "metrics": {
                    "conviction": {"point": 0.61, "raw": 0.58, "ci_90": [0.55, 0.67]},
                    "consensus": {"n_bullish": 2, "n_models_active": 3, "disagreement_std": 0.05},
                    "regime": {"state": "lateral", "proba": {"bull": 0.3, "lateral": 0.5, "bear": 0.2}},
                },
            },
        ],
        "actionable_bets_bmv": [],
        "insights": [{"tipo": "Consenso fuerte", "texto": "WALMEX consenso alto"}],
    }


def test_build_insights_bundle_schema():
    bundle = build_insights_bundle(_sample_super_result())
    assert bundle.schema_version == "1.0"
    assert len(bundle.top_picks) == 1
    assert bundle.top_picks[0].ticker == "WALMEX"
    assert bundle.portfolio is not None
    assert bundle.portfolio.apostar == ["WALMEX"]
    assert len(bundle.universes) == 1
    assert bundle.universes[0].models[0].auc == 0.54


def test_item_to_insight_incertidumbres():
    item = _sample_super_result()["master_ranking"][0]
    ins = _item_to_insight(item)
    assert ins.veredicto == "APOSTAR"
    assert any("IC90" in x for x in ins.incertidumbres)


def test_bundle_json_roundtrip():
    bundle = build_insights_bundle(_sample_super_result())
    raw = bundle.model_dump_json()
    back = InsightsBundle.model_validate_json(raw)
    assert back.n_tickers == bundle.n_tickers
