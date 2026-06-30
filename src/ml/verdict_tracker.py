"""
Gemini Verdict Tracker — append-only log of CONFIRMA/DEGRADA/VETA decisions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERDICT_LOG_PATH = PROJECT_ROOT / "data" / "gemini_verdicts.jsonl"


def log_verdict(ticker: str, item: dict, verdict: dict) -> None:
    """
    Append one Gemini validation verdict to data/gemini_verdicts.jsonl.

    Parameters
    ----------
    ticker  : instrument short name
    item    : ranking item passed to validate_item (conviction, signals, etc.)
    verdict : parsed Gemini response or fallback verdict
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "veredicto": verdict.get("veredicto"),
        "accion_final": verdict.get("accion_final"),
        "confianza_gemini": verdict.get("confianza_gemini"),
        "conviction": item.get("conviction"),
        "disagreement": item.get("disagreement"),
        "regime": item.get("regime"),
        "rank_global": item.get("rank_global"),
        "news_alerta": item.get("news_alerta", False),
        "fallback": bool(verdict.get("_fallback", False)),
        "tesis": (verdict.get("tesis") or "")[:300],
    }

    try:
        VERDICT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with VERDICT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"verdict_tracker log failed for {ticker}: {e}")
