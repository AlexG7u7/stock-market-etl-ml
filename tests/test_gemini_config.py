"""Tests for centralized Gemini model config."""
from __future__ import annotations

import os

from src.ml.gemini_config import DEFAULT_MODELS, content_config, get_model


def test_default_models_best_tier() -> None:
    assert DEFAULT_MODELS["trader"] == "gemini-2.5-pro"
    assert DEFAULT_MODELS["validator"] == "gemini-2.5-pro"
    assert DEFAULT_MODELS["analyst"] == "gemini-2.5-flash"
    assert DEFAULT_MODELS["news"] == "gemini-2.5-flash-lite"


def test_get_model_env_override(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL_TRADER", "gemini-custom")
    assert get_model("trader") == "gemini-custom"


def test_content_config_thinking_off() -> None:
    class FakeThinking:
        def __init__(self, thinking_budget: int) -> None:
            self.thinking_budget = thinking_budget

    class FakeTypes:
        ThinkingConfig = FakeThinking

        @staticmethod
        def GenerateContentConfig(**kwargs):
            return kwargs

    cfg = content_config(FakeTypes(), system_instruction="sys", max_output_tokens=100)
    assert cfg["system_instruction"] == "sys"
    assert cfg["thinking_config"].thinking_budget == 0
