"""Tests for agent knowledge loader."""
from __future__ import annotations

from src.ml.knowledge_loader import (
    KNOWLEDGE_FILES,
    format_knowledge_for_prompt,
    get_knowledge_prompt,
    load_agent_knowledge,
)


def test_load_agent_knowledge_has_all_files():
    knowledge = load_agent_knowledge()
    for fname in KNOWLEDGE_FILES:
        key = fname.removesuffix(".yaml")
        assert key in knowledge
        assert isinstance(knowledge[key], dict)


def test_literature_rules_loaded():
    knowledge = load_agent_knowledge()
    rules = knowledge["literature_rules"].get("rules", [])
    ids = {r["id"] for r in rules if isinstance(r, dict) and "id" in r}
    assert "LR-001" in ids
    assert "LR-012" in ids


def test_format_knowledge_for_prompt_non_empty():
    knowledge = load_agent_knowledge()
    prompt = format_knowledge_for_prompt(knowledge, role="validator")
    assert prompt
    assert "LR-001" in prompt
    assert "DECISION PROTOCOL" in prompt
    assert len(prompt) <= 7600


def test_format_analyst_includes_bmv():
    prompt = get_knowledge_prompt(role="analyst")
    assert "BMV OPERATIONAL RULES" in prompt
