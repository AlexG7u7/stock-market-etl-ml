"""Chat completions con tools contra la API de xAI."""
from __future__ import annotations

import os
from typing import Any

import httpx

API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4"


def function_tool(schema: dict) -> dict:
    """Pasa el tool_schema() (name, description, input_schema) al formato de chat completions."""
    if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
        return schema
    parameters = schema.get("input_schema") or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema.get("description") or "",
            "parameters": parameters,
        },
    }


def chat_with_tools(messages: list[dict], tools: list[dict], model: str | None = None) -> dict[str, Any]:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta XAI_API_KEY")
    model = model or os.getenv("XAI_MODEL", DEFAULT_MODEL)
    response = httpx.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": [function_tool(tool) for tool in tools],
        },
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"xAI {response.status_code}: {response.text[:500]}")
    return response.json()
