"""
Contexto de mercado en vivo vía DataBursátil + sentimiento opcional con LLM.

IMPORTANTE — qué es y qué NO es:
  La API gratuita de DataBursátil expone tasas/índices/divisas como SNAPSHOT
  ACTUAL (no series históricas) y noticias solo DEL DÍA. Por eso estos datos:
    ✅ Sirven como CONTEXTO en vivo para la decisión diaria (info nueva real).
    ❌ NO se pueden backtestear (no hay historia para entrenar/validar).

  Para datos macro históricos backtesteables (tasas con historia) habría que
  usar la API SIE de Banxico (requiere su propio token).

Sentimiento con LLM:
  Si existe OPENAI_API_KEY o ANTHROPIC_API_KEY en el entorno, score_news_sentiment()
  resume y puntúa el sentimiento de las noticias del día. Sin key, degrada
  elegantemente devolviendo None (no rompe el pipeline).
"""
from __future__ import annotations

import os
import logging

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.databursatil.com"
TIMEOUT  = 20

# Tasas e índices de interés para acciones mexicanas (tickers validados)
RATE_TICKERS  = "TIIE28,CETE28,Tasa_Objetivo"
INDEX_TICKERS = "IPC,SP500"


def _get(endpoint: str, params: dict, token: str) -> dict | None:
    params = {**params, "token": token}
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Error" in data:
            logger.warning(f"{endpoint}: {data['Error']}")
            return None
        return data
    except Exception as e:
        logger.warning(f"{endpoint} falló: {e}")
        return None


def get_rates(token: str) -> dict:
    """Tasas de mercado de dinero (snapshot actual). {ticker: {tasa, fecha}}."""
    data = _get("/v2/tasas", {"ticker": RATE_TICKERS}, token) or {}
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = {"tasa": v.get("t"), "fecha": v.get("f")}
    return out


def get_indices(token: str) -> dict:
    """Índices bursátiles (snapshot actual). {ticker: {nivel, cambio_pct, ...}}."""
    data = _get("/v2/indices", {"ticker": INDEX_TICKERS}, token) or {}
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = {
                "nivel":      v.get("u"),
                "cambio_pct": v.get("c"),
                "ytd_pct":    v.get("ytdp"),
                "fecha":      v.get("f"),
            }
    return out


def get_news(token: str, categorias: str = "top,generales,flash") -> list[dict]:
    """Cables noticiosos del día de emisoras mexicanas y economía."""
    data = _get("/v2/cables", {"categorias": categorias}, token) or {}
    news = []
    if isinstance(data, dict):
        for cat, items in data.items():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        news.append({
                            "categoria": cat,
                            "titulo":    it.get("titulo") or it.get("t") or it.get("headline"),
                            "fecha":     it.get("fecha")  or it.get("f"),
                            "resumen":   it.get("resumen") or it.get("texto") or it.get("descripcion"),
                        })
    return news


def market_context(token: str) -> dict:
    """Snapshot completo de contexto: tasas + índices + noticias."""
    rates   = get_rates(token)
    indices = get_indices(token)
    news    = get_news(token)

    # Señal simple de entorno de tasas: ¿la tasa objetivo va alta? (riesgo para equities)
    tasa_obj = rates.get("Tasa_Objetivo", {}).get("tasa")
    ipc_chg  = indices.get("IPC", {}).get("cambio_pct")

    return {
        "rates":   rates,
        "indices": indices,
        "news":    news[:15],
        "n_news":  len(news),
        "tasa_objetivo": tasa_obj,
        "ipc_cambio_pct": ipc_chg,
    }


# ─── Sentimiento con LLM (opcional, degrada si no hay key) ──────────────────────

def score_news_sentiment(news: list[dict]) -> dict | None:
    """
    Puntúa el sentimiento de las noticias del día con Gemini 2.5-flash.
    Requiere GEMINI_API_KEY en el entorno.
    Devuelve None si no hay key o no hay noticias.

    Returns:
        {"score": -1..1, "etiqueta": "...", "resumen": "...", "n": int}  o  None
    """
    if not news:
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    headlines = "\n".join(f"- {n.get('titulo','')}" for n in news if n.get("titulo"))
    if not headlines.strip():
        return None

    prompt = (
        "Eres un analista financiero. Con base en estos titulares del día sobre "
        "el mercado mexicano, da un puntaje de sentimiento de mercado entre -1 "
        "(muy negativo) y +1 (muy positivo), una etiqueta corta y un resumen de "
        "una frase. Responde SOLO en JSON: "
        '{\"score\": float, \"etiqueta\": str, \"resumen\": str}.\n\n'
        f"Titulares:\n{headlines}"
    )

    import json as _json

    def _parse_json(text: str) -> dict:
        """Extrae JSON de respuestas que pueden venir con bloques ```json ... ```."""
        txt = text.strip()
        # Quitar bloque markdown si viene envuelto
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        start = txt.find("{")
        end   = txt.rfind("}") + 1
        return _json.loads(txt[start:end])

    try:
        from google import genai                        # type: ignore[import]
        from google.genai import types as genai_types   # type: ignore[import]
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.2,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        res = _parse_json(response.text or "")
        res["n"] = len(news)
        return res
    except Exception as e:
        logger.warning(f"Sentimiento Gemini falló: {e}")
        return None
