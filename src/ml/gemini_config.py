"""
Configuración centralizada de modelos Gemini por rol.

Override vía .env:
  GEMINI_MODEL_TRADER=gemini-2.5-pro
  GEMINI_MODEL_VALIDATOR=gemini-2.5-pro
  GEMINI_MODEL_ANALYST=gemini-2.5-flash
  GEMINI_MODEL_NEWS=gemini-2.5-flash-lite
  GEMINI_MODEL_MARKET=gemini-2.5-flash
"""
from __future__ import annotations

import os
from typing import Any

# trader/validator → pro (razonamiento + JSON estructurado)
# analyst/market → flash (balance calidad/latencia)
# news → flash-lite (alto volumen, tarea simple)
DEFAULT_MODELS: dict[str, str] = {
    "trader": "gemini-2.5-pro",
    "validator": "gemini-2.5-pro",
    "analyst": "gemini-2.5-flash",
    "news": "gemini-2.5-flash-lite",
    "market": "gemini-2.5-flash",
}


def get_model(role: str) -> str:
    """Modelo Gemini para un rol (`trader`, `validator`, `analyst`, `news`, `market`)."""
    env_key = f"GEMINI_MODEL_{role.upper()}"
    return os.getenv(env_key) or DEFAULT_MODELS.get(role, "gemini-2.5-flash")


def create_client() -> tuple[Any, Any] | tuple[None, None]:
    """(genai.Client, genai.types) o (None, None) si no hay API key."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, None
    try:
        from google import genai
        from google.genai import types as genai_types
        return genai.Client(api_key=api_key), genai_types
    except Exception:
        return None, None


def content_config(
    genai_types: Any,
    *,
    system_instruction: str | None = None,
    max_output_tokens: int = 800,
    temperature: float = 0.2,
    thinking_budget: int = 0,
) -> Any:
    """GenerateContentConfig con thinking desactivado (evita truncar JSON)."""
    kwargs: dict[str, Any] = {
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
    }
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if thinking_budget is not None and hasattr(genai_types, "ThinkingConfig"):
        kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=thinking_budget)
    return genai_types.GenerateContentConfig(**kwargs)


def generate_json(
    client: Any,
    role: str,
    contents: str,
    genai_types: Any,
    *,
    system_instruction: str | None = None,
    max_output_tokens: int = 800,
    temperature: float = 0.2,
) -> str:
    """Llama a Gemini y retorna texto crudo."""
    resp = client.models.generate_content(
        model=get_model(role),
        contents=contents,
        config=content_config(
            genai_types,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
    )
    return (resp.text or "").strip()
