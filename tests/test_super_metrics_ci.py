"""Tests for format_metrics_for_prompt edge cases."""
from src.ml.super_metrics import format_metrics_for_prompt


def test_format_metrics_handles_none_ci():
    item = {
        "metrics": {
            "conviction": {"point": 0.6, "ci_90": [0.5, 0.7], "raw": 0.58},
            "consensus": {"n_bullish": 3, "n_models_active": 4, "disagreement_std": 0.1},
            "models": {
                "xs_lgbm": {
                    "score": 0.62,
                    "weight": 0.25,
                    "auc": 0.52,
                    "auc_ci_90": None,
                },
            },
        },
    }
    txt = format_metrics_for_prompt(item)
    assert "xs_lgbm" in txt
    assert "?" in txt
