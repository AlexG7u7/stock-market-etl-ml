"""
Agent Knowledge Loader — reads YAML rules from articles/knowledge/agent/
and compacts them for Gemini system prompts (~2000 tokens max).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_KNOWLEDGE_DIR = PROJECT_ROOT / "articles" / "knowledge" / "agent"

KNOWLEDGE_FILES: tuple[str, ...] = (
    "decision_protocol.yaml",
    "literature_rules.yaml",
    "risk_limits.yaml",
    "calibration.yaml",
    "failure_modes.yaml",
    "bmv_market_rules.yaml",
)

# ~2000 tokens ≈ 7500 chars for mixed ES/EN technical text
MAX_PROMPT_CHARS = 7500


def load_agent_knowledge() -> dict:
    """Load all agent YAML knowledge files into a dict keyed by stem name."""
    knowledge: dict = {}
    for fname in KNOWLEDGE_FILES:
        path = AGENT_KNOWLEDGE_DIR / fname
        key = fname.removesuffix(".yaml")
        if path.exists():
            with path.open(encoding="utf-8") as f:
                knowledge[key] = yaml.safe_load(f) or {}
        else:
            knowledge[key] = {}
    return knowledge


from src.ml.literature_rag import query_literature


@lru_cache(maxsize=4)
def _format_cached(role: str) -> str:
    return format_knowledge_for_prompt(load_agent_knowledge(), role=role)


def get_knowledge_prompt(role: str = "validator", *, literature_query: str | None = None) -> str:
    """Cached knowledge prompt for Gemini system instructions."""
    base = _format_cached(role)
    if literature_query:
        lit = query_literature(literature_query, top_k=4)
        if lit:
            base = f"{base}\n\n{lit}"
    return base


def format_knowledge_for_prompt(knowledge: dict, *, role: str = "validator") -> str:
    """
    Compact agent rules for LLM context.

    Parameters
    ----------
    knowledge : output of load_agent_knowledge()
    role      : 'validator' (risk committee) or 'analyst' (executive analysis)
    """
    sections: list[str] = []

    _append_decision_protocol(knowledge, sections)
    _append_literature_rules(knowledge, sections)
    _append_risk_limits(knowledge, sections)
    _append_calibration(knowledge, sections)
    _append_failure_modes(knowledge, sections)
    if role in ("analyst", "validator", "trader"):
        _append_bmv_rules(knowledge, sections, full=(role in ("analyst", "trader")))

    text = "\n\n".join(sections)
    if len(text) > MAX_PROMPT_CHARS:
        text = text[: MAX_PROMPT_CHARS - 40] + "\n... [truncated for token budget]"
    return text


def _append_decision_protocol(knowledge: dict, sections: list[str]) -> None:
    dp = knowledge.get("decision_protocol", {})
    if not dp:
        return

    steps = dp.get("decision_pipeline", [])
    step_lines: list[str] = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        rule_ids = [
            r.get("id", "")
            for r in s.get("rules", [])
            if isinstance(r, dict) and r.get("id")
        ]
        step_lines.append(
            f"  Step {s.get('step', '?')} ({s.get('name', '?')}): {', '.join(rule_ids)}"
        )
    if step_lines:
        sections.append("DECISION PROTOCOL (follow step 4 for validation):\n" + "\n".join(step_lines))

    matrix = dp.get("bet_sizing_matrix", [])
    if matrix:
        matrix_lines = [
            f"  conv={m.get('conviction', '?')} + gemini={m.get('gemini', '?')} "
            f"→ max {m.get('max_pct', 0)}% ({m.get('label', '')})"
            for m in matrix
            if isinstance(m, dict)
        ]
        sections.append("BET SIZING (conviction × Gemini):\n" + "\n".join(matrix_lines[:6]))


def _append_literature_rules(knowledge: dict, sections: list[str]) -> None:
    lr = knowledge.get("literature_rules", {})
    rules = lr.get("rules", [])
    if not rules:
        return

    lr_lines = [
        f"  {r.get('id', '?')} [{r.get('priority', '?')}]: {r.get('rule', '')} "
        f"→ {r.get('agent_policy', '')}"
        for r in rules
        if isinstance(r, dict)
    ]
    sections.append(
        "LITERATURE RULES (MUST cite LR-xxx IDs in evidencia/red_flags when applicable):\n"
        + "\n".join(lr_lines)
    )

    never = lr.get("agent_never_do", [])
    if never:
        never_lines = [f"  ✗ {n.get('rule', '')}" for n in never if isinstance(n, dict)]
        sections.append("NEVER DO:\n" + "\n".join(never_lines))


def _append_risk_limits(knowledge: dict, sections: list[str]) -> None:
    rl = knowledge.get("risk_limits", {})
    if not rl:
        return

    hard = rl.get("hard_limits", {})
    if hard:
        hard_str = ", ".join(f"{k}={v}" for k, v in hard.items())
        sections.append(f"HARD LIMITS (never violate): {hard_str}")

    cbs = rl.get("circuit_breakers", [])
    cb_lines = [
        f"  {c.get('id', '')}: {c.get('trigger', '')} → {c.get('action', '')}"
        for c in cbs
        if isinstance(c, dict)
    ]
    if cb_lines:
        sections.append("CIRCUIT BREAKERS:\n" + "\n".join(cb_lines))


def _append_calibration(knowledge: dict, sections: list[str]) -> None:
    cal = knowledge.get("calibration", {})
    if not cal:
        return

    live = cal.get("live_stats", {})
    if live:
        sections.append(
            "LIVE CALIBRATION (paper trades):\n"
            f"  source={live.get('source', '?')}, n={live.get('n_closed', 0)}, "
            f"win_rate={live.get('win_rate', '?')}, "
            f"avg_win={live.get('avg_win_pct', '?')}%, "
            f"avg_loss={live.get('avg_loss_pct', '?')}%, "
            f"sharpe≈{live.get('sharpe_approx', '?')}"
        )
        return

    mp = cal.get("model_performance", {})
    if mp:
        sections.append(
            "HISTORICAL CALIBRATION (walk-forward):\n"
            f"  win_rate={mp.get('win_rate')}, avg_win={mp.get('avg_win_pct')}%, "
            f"avg_loss={mp.get('avg_loss_pct')}%, payoff={mp.get('payoff_ratio')}"
        )


def _append_failure_modes(knowledge: dict, sections: list[str]) -> None:
    fm = knowledge.get("failure_modes", {})
    if not fm:
        return

    fm_lines = [
        f"  {key}: {val['agent_action']}"
        for key, val in fm.items()
        if isinstance(val, dict) and val.get("agent_action")
    ]
    if fm_lines:
        sections.append("FAILURE MODES (degrade or skip when triggered):\n" + "\n".join(fm_lines[:8]))


def _append_bmv_rules(knowledge: dict, sections: list[str], *, full: bool) -> None:
    bmv = knowledge.get("bmv_market_rules", {})
    if not bmv:
        return

    lines: list[str] = []
    session = bmv.get("session", {})
    if session:
        lines.append(f"  Session: {session.get('regular_hours', '')} CDMX")
        lines.append(f"  Entry: {session.get('entry_preference', '')}")
        if full:
            lines.append(f"  Avoid: {session.get('avoid', '')}")

    costs = bmv.get("costs", {})
    if costs:
        lines.append(f"  Round-trip cost est: {costs.get('total_round_trip_estimate_pct', '?')}%")

    pc = bmv.get("position_constraints", {})
    if pc:
        lines.append(
            f"  Max open={pc.get('max_open_positions')}, "
            f"max single={pc.get('max_single_name_pct')}%, "
            f"cash buffer={pc.get('cash_buffer_pct')}%"
        )

    universes = bmv.get("universes", {})
    if full and universes:
        for slug, info in universes.items():
            if isinstance(info, dict):
                lines.append(f"  Universe {slug}: priority={info.get('agent_priority', '?')}")

    if lines:
        sections.append("BMV OPERATIONAL RULES:\n" + "\n".join(lines))
