"""Agente inversor: una conversación con tools. Claude pide la tool y los parámetros."""
from __future__ import annotations

import json
import os
from typing import Any

from src.agent.base import Agent
from src.agent.book import Book
from src.agent.chat import chat_with_tools, function_tool
from src.agent.policy import PoliticaInversor
from src.agent.tools import asignacion_schema, build_tools, price_usd

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_ROUNDS = 8


class AgenteInversor(Agent):
    name = "inversor"

    def __init__(self, book: Book, policy: PoliticaInversor | None = None, model: str | None = None):
        self.book = book
        self.policy = policy or PoliticaInversor()
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.tools = build_tools(book)

    def observe(self, **params) -> dict:
        schemas = [a.tool_schema() for a in self.tools.values()]
        schemas.append(asignacion_schema())
        return {
            "system": self.policy.system_prompt(),
            "user": self.policy.user_message(self.book),
            "tools": [function_tool(schema) for schema in schemas],
            "model": self.model,
        }

    def dispatch(self, name: str, params: dict | None) -> dict:
        params = params or {}
        agent = self.tools.get(name)
        if agent is None:
            return {"ok": False, "error": f"tool desconocida: {name}"}
        try:
            return agent.observe(**params)
        except TypeError as exc:
            return {"ok": False, "error": f"parametros de {name}: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"{name} fallo: {exc}"}

    def act(self, observation: dict | None = None, apply: bool = False) -> dict:
        pregunta = observation or self.observe()
        if not os.getenv("ANTHROPIC_API_KEY"):
            return {
                "ok": False,
                "error": "Falta ANTHROPIC_API_KEY en el entorno. La pregunta ya está armada.",
                "pregunta": pregunta,
            }

        messages: list[dict] = [
            {"role": "system", "content": pregunta["system"]},
            {"role": "user", "content": pregunta["user"]},
        ]
        transcript: list[dict] = []
        asignacion = None

        for _ in range(MAX_ROUNDS):
            resp = chat_with_tools(messages, pregunta["tools"], self.model)
            choice = (resp.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            transcript.append({"finish_reason": choice.get("finish_reason"), "message": message})
            if not tool_calls:
                break

            messages.append(_assistant_message(message))
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                args, error = _arguments(fn.get("arguments"))
                if error:
                    payload = {"ok": False, "error": error}
                elif name == "proponer_asignacion":
                    prices = _prices_for(args)
                    payload = self.policy.guard(args, self.book, prices)
                    if payload.get("ok"):
                        asignacion = payload
                        asignacion["prices_usd"] = prices
                else:
                    payload = self.dispatch(name, args)
                messages.append(_tool_message(call.get("id"), payload))
            if asignacion:
                break

        applied = None
        if asignacion and apply:
            applied = self.book.apply(asignacion, asignacion["prices_usd"])

        return {
            "ok": asignacion is not None,
            "modelo": self.model,
            "asignacion": {k: asignacion[k] for k in ("allocations", "cash_usd", "motivo") if k in (asignacion or {})} if asignacion else None,
            "aplicado": applied,
            "turnos": len(transcript),
            "transcript": transcript,
        }


def _prices_for(proposal: dict) -> dict[str, float]:
    out = {}
    for row in proposal.get("allocations") or []:
        ticker = str(row.get("ticker", "")).upper()
        if not ticker:
            continue
        quote = price_usd(ticker)
        if quote.get("ok"):
            out[ticker] = float(quote["precio_usd"])
    return out


def _arguments(raw: Any) -> tuple[dict, str | None]:
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"arguments invalidos: {exc}"
    if not isinstance(parsed, dict):
        return {}, "arguments tiene que ser un objeto"
    return parsed, None


def _assistant_message(message: dict) -> dict:
    out: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
    calls = message.get("tool_calls") or []
    if calls:
        out["tool_calls"] = calls
    return out


def _tool_message(tool_call_id: str | None, payload: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(payload, ensure_ascii=False),
    }
