"""
Gemini Validator — capa 4 del super modelo.

Gemini NO genera recomendaciones. Recibe la decisión cuantitativa del SuperModel
+ toda la evidencia, y actúa como comité de riesgo: CONFIRMA, DEGRADA o VETA,
citando los datos reales. Esto lo hace auditable y anti-alucinación.

Contrato de salida (JSON estricto):
    {
      "veredicto": "CONFIRMA | DEGRADA | VETA",
      "confianza_gemini": 0-100,
      "tesis": "narrativa de inversión",
      "evidencia_a_favor": [...],
      "red_flags": [...],
      "accion_final": "COMPRA FUERTE | COMPRA | ESPERA | EVITA"
    }

Degradación elegante: sin GEMINI_API_KEY o ante error, devuelve un veredicto
neutral derivado de la convicción del modelo (el super modelo sigue mandando).
"""
from __future__ import annotations

import json
import logging
import os
import time

from src.ml.gemini_config import create_client, generate_json, get_model
from src.ml.knowledge_loader import get_knowledge_prompt
from src.ml.literature_rag import query_literature
from src.ml.super_metrics import MODEL_LABELS, format_metrics_for_prompt
from src.ml.verdict_tracker import log_verdict

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Eres el comité de riesgo de un fondo cuantitativo BMV long-only. "
    "Validas recomendaciones del modelo cuantitativo; NO predices precios. "
    "Debes seguir el protocolo de decisión (step 4: validacion_gemini) y "
    "citar reglas LR-xxx de la literatura cuando apliquen en evidencia_a_favor o red_flags.\n\n"
    + get_knowledge_prompt(role="validator")
)


def _fallback_verdict(item: dict) -> dict:
    """Veredicto determinista cuando Gemini no está disponible."""
    conv = item.get("conviction", 0.5)
    disagreement = item.get("disagreement", 0.0)
    news_alerta = item.get("news_alerta", False)

    if news_alerta:
        veredicto, accion = "DEGRADA", "ESPERA"
    elif conv >= 0.65 and disagreement < 0.15:
        veredicto, accion = "CONFIRMA", "COMPRA FUERTE"
    elif conv >= 0.55:
        veredicto, accion = "CONFIRMA", "COMPRA"
    elif conv >= 0.45:
        veredicto, accion = "DEGRADA", "ESPERA"
    else:
        veredicto, accion = "VETA", "EVITA"

    return {
        "veredicto": veredicto,
        "confianza_gemini": int(min(conv * 100, 99)),
        "tesis": f"Convicción del modelo {conv:.2f} con desacuerdo {disagreement:.2f}. "
                 f"Veredicto automático (Gemini no disponible).",
        "evidencia_a_favor": [f"Convicción {conv:.2f}", f"Régimen {item.get('regime','?')}"],
        "red_flags": (["Noticias negativas detectadas"] if news_alerta else []),
        "accion_final": accion,
        "_fallback": True,
    }


def _build_prompt(item: dict, result: dict | None = None) -> str:
    signals_txt = "\n".join(
        f"    - {MODEL_LABELS.get(m, m)} ({m}): {v:.3f}  "
        f"(peso fusión {item.get('model_weights', {}).get(m, 0):.3f}, "
        f"AUC OOS {item.get('model_auc', {}).get(m, 0.5):.3f})"
        for m, v in item.get("signals", {}).items()
    )
    headlines = item.get("headlines") or []
    news_txt = "\n".join(f"    • {h}" for h in headlines[:5]) or "    (sin titulares recientes)"
    news_sent = item.get("news_sent")
    news_sent_txt = f"{news_sent:+.2f}" if news_sent is not None else "n/d"
    metrics_block = ""
    if item.get("metrics"):
        metrics_block = f"\nMÉTRICAS E INCERTIDUMBRES:\n{format_metrics_for_prompt(item)}\n"

    slug = item.get("universe_slug", "")
    um = ((result or {}).get("universe_metrics") or {}).get(slug, {})
    fusion = um.get("fusion", {})
    fusion_txt = (
        f"  Modo: {item.get('fusion_mode', fusion.get('selected', '?'))}\n"
        f"  Stack AUC holdout: {item.get('stack_auc', fusion.get('stack_auc', 'n/d'))}\n"
        f"  AUC-weight holdout: {item.get('fusion_auc', fusion.get('auc_weight_auc', 'n/d'))}"
    )

    registry = (result or {}).get("model_registry", {})
    active = [m["id"] for m in registry.get("core_models", []) if m.get("active")]
    arch_txt = f"Modelos activos: {', '.join(active) or 'xs_lgbm, ensemble, heuristic, lstm_seq'}"

    lit_ctx = query_literature(
        f"stock prediction {item.get('universe_slug', '')} LSTM validation risk",
        top_k=3,
    )
    literature_block = f"\nLITERATURA RAG:\n{lit_ctx}\n" if lit_ctx else ""

    return f"""Valida la recomendación del modelo para {item['ticker']} ({item.get('universe_slug','?')}, {item.get('moneda','?')}).
{literature_block}
{metrics_block}
ARQUITECTURA: {arch_txt}
FUSIÓN L2:
{fusion_txt}

PROTOCOLO (step 4 — validacion_gemini):
  - CONFIRMA → acciones COMPRA FUERTE / COMPRA → bet_action PROCEED
  - DEGRADA → ESPERA → REDUCE_SIZE_50pct o SKIP
  - VETA → EVITA → NO_BET (circuit breaker CB-GEMINI-VETO)
  - Si news_alerta → NO_BET_OR_ESPERA (LR-003, LR-005)

DECISIÓN DEL MODELO (no la cuestiones sin evidencia):
  Ranking global: #{item.get('rank_global','?')} de {item.get('n_total','?')}
  Convicción: {item.get('conviction',0):.3f} (0-1, mayor = mejor)
  Desacuerdo entre modelos: {item.get('disagreement',0):.3f}
  Precio actual: {item.get('precio','?')}

PREDICCIÓN DE CADA MODELO BASE:
{signals_txt}

CONTEXTO:
  Régimen de mercado: {item.get('regime','?')} (factor ×{item.get('regime_factor',1.0)})
  Sentimiento noticias: {news_sent_txt}
  Titulares recientes:
{news_txt}

Tu trabajo NO es predecir el precio. Es VALIDAR la recomendación del modelo:
  - Si la evidencia la respalda → CONFIRMA
  - Si hay señales mixtas o desacuerdo alto → DEGRADA y explica (LR-007 si disagreement > 0.20)
  - Si ves un riesgo grave que el modelo no captura → VETA

En evidencia_a_favor y red_flags, cita reglas LR-xxx cuando apliquen (ej. "LR-003: noticias contradicen momentum").

Responde SOLO con JSON (sin markdown):
{{"veredicto": "CONFIRMA|DEGRADA|VETA",
  "confianza_gemini": <0-100>,
  "tesis": "<2-3 frases de tesis de inversión basada en la evidencia>",
  "evidencia_a_favor": ["<punto citando datos y LR-xxx si aplica>", "..."],
  "red_flags": ["<riesgo concreto con LR-xxx si aplica>", "..."],
  "accion_final": "COMPRA FUERTE|COMPRA|ESPERA|EVITA"}}"""


def _fetch_headlines(ticker: str, sym: str, slug: str, max_items: int = 5) -> list[str]:
    try:
        from src.api.gemini_analyst import fetch_news_for_ticker
        news = fetch_news_for_ticker(ticker, sym, slug, max_items=max_items)
        return [n.get("title", "") for n in news if n.get("title")]
    except Exception as e:
        logger.debug(f"headlines {ticker}: {e}")
        return []


def validate_item(item: dict, client=None, genai_types=None, result: dict | None = None) -> dict:
    """Valida un solo ticker con Gemini (o fallback)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or client is None:
        verdict = _fallback_verdict(item)
        log_verdict(item["ticker"], item, verdict)
        return verdict

    try:
        prompt = _build_prompt(item, result)
        txt = generate_json(
            client, "validator", prompt, genai_types,
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=900,
            temperature=0.2,
        )
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        start, end = txt.find("{"), txt.rfind("}") + 1
        if start >= 0 and end > start:
            verdict = json.loads(txt[start:end])
            verdict["_fallback"] = False
            verdict["_model"] = get_model("validator")
            log_verdict(item["ticker"], item, verdict)
            return verdict
    except Exception as e:
        logger.warning(f"Gemini validate {item['ticker']}: {e}")

    verdict = _fallback_verdict(item)
    log_verdict(item["ticker"], item, verdict)
    return verdict


def validate_ranking(
    result: dict,
    tickers_map: dict[str, str] | None = None,
    top_n: int | None = None,
) -> dict:
    """
    Valida el top-N del ranking maestro con Gemini.

    Parameters
    ----------
    result      : salida de SuperModel.run()
    tickers_map : nombre_corto → símbolo yfinance (para descargar titulares)
    top_n       : cuántos validar (default: result["top_gemini"])

    Returns
    -------
    El mismo result con result["master_ranking"][i]["gemini"] poblado en el top-N.
    """
    ranking = result.get("master_ranking", [])
    if not ranking:
        return result

    top_n = top_n or result.get("top_gemini", 10)
    n_total = len(ranking)
    tickers_map = tickers_map or {}

    client, genai_types = create_client()
    if client is None and os.getenv("GEMINI_API_KEY"):
        logger.warning("Gemini init failed")

    n_confirma = n_degrada = n_veta = 0

    for item in ranking[:top_n]:
        item["n_total"] = n_total
        sym = tickers_map.get(item["ticker"], item["ticker"])
        if client is not None:
            item["headlines"] = _fetch_headlines(
                item["ticker"], sym, item.get("universe_slug", ""))
        verdict = validate_item(item, client, genai_types, result=result)
        item["gemini"] = verdict

        v = verdict.get("veredicto", "")
        n_confirma += v == "CONFIRMA"
        n_degrada  += v == "DEGRADA"
        n_veta     += v == "VETA"

        if client is not None and not verdict.get("_fallback"):
            time.sleep(1.5)  # rate limit

    result["gemini_summary"] = {
        "validados": min(top_n, n_total),
        "confirma": n_confirma,
        "degrada": n_degrada,
        "veta": n_veta,
        "modo": "gemini" if client is not None else "fallback",
        "agent": "gemini_validator",
        "model": get_model("validator"),
    }
    return result
