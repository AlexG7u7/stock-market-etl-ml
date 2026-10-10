#!/usr/bin/env python3
"""Un ciclo del agente inversor.

    python scripts/run_investor_agent.py --ejemplo
    python scripts/run_investor_agent.py            # llama a Grok si hay XAI_API_KEY
    python scripts/run_investor_agent.py --aplicar  # además escribe el libro
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.agent.book import Book
from src.agent.investor import AgenteInversor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejemplo", action="store_true", help="Imprime la pregunta y un tool call, sin llamar a Grok")
    parser.add_argument("--aplicar", action="store_true", help="Si Grok acepta, escribe data/agent/book.json")
    args = parser.parse_args()

    book = Book(ROOT / "data" / "agent" / "book.json")
    agent = AgenteInversor(book)

    if args.ejemplo:
        pregunta = agent.observe()
        demo_call = {"type": "tool_use", "name": "ver_ranking", "input": {"universo": "bmv", "horizonte": "4s"}}
        demo_result = agent.dispatch("ver_ranking", demo_call["input"])
        print(json.dumps({
            "system": pregunta["system"],
            "user": pregunta["user"],
            "tools": [t["function"]["name"] for t in pregunta["tools"]],
            "ejemplo_respuesta_de_claude": demo_call,
            "resultado_de_esa_tool": demo_result,
        }, ensure_ascii=False, indent=2))
        return

    result = agent.act(apply=args.aplicar)
    if not result.get("ok") and result.get("pregunta"):
        print(result["error"])
        print(json.dumps({"user": result["pregunta"]["user"]}, ensure_ascii=False, indent=2))
        return
    slim = {k: result[k] for k in ("ok", "modelo", "asignacion", "aplicado", "turnos")}
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
