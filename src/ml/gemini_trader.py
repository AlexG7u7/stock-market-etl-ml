"""
Gemini Trader Agent — capa 4 del SuperModel (modo insights).

Recibe métricas cuantitativas con incertidumbres (super_metrics) y actúa como
trader profesional BMV: dónde apostar, cómo (tamaño/horizonte), qué evitar.

No reemplaza el risk engine determinista; sintetiza evidencia para el consumidor.
"""
from __future__ import annotations

import json
import logging
import os

from src.ml.gemini_config import create_client, generate_json, get_model
from src.ml.knowledge_loader import get_knowledge_prompt
from src.ml.super_metrics import MODEL_LABELS, format_metrics_for_prompt
from src.ml.verdict_tracker import log_verdict

logger = logging.getLogger(__name__)

TRADER_SYSTEM_PROMPT = (
    "Eres un trader profesional de renta variable BMV con book propio (long-only, 5–20 días). "
    "NO eres un narrador pasivo: simulas ser el trader que decide si pone dinero real.\n\n"
    "Hablas en PRIMERA PERSONA ('yo apostaría', 'no tocaría este nombre', 'esperaría pullback'). "
    "Recibes outputs de un SuperModel con 4 predictores fusionados más métricas OOS con IC90.\n\n"
    "Tu trabajo:\n"
    "  1. Dar TU perspectiva clara: ¿apostarías sí o no, y por qué?\n"
    "  2. Veredicto operativo: APOSTAR (entrar), ESPERAR (vigilar/monitor), EVITAR (no tocar).\n"
    "  3. Explicar CÓMO apostarías: tamaño, horizonte, entrada, stop/gestión.\n"
    "  4. Citar reglas LR-xxx cuando apliquen.\n"
    "  5. Si AUC IC90 cruza 0.50 → señal débil; dilo explícitamente.\n"
    "  6. Desacuerdo alto entre modelos → tú también dudarías; preferir ESPERAR.\n"
    "  7. paper_only: el usuario decide al final, pero tú das tu opinión de trader sin ambigüedad.\n\n"
    + get_knowledge_prompt(role="trader")
)


def _fallback_trader(item: dict) -> dict:
    conv = float(item.get("conviction", 0.5))
    dis = float(item.get("disagreement", 0))
    news_alerta = item.get("news_alerta", False)
    m = item.get("metrics") or {}
    ci = m.get("consensus", {})

    if news_alerta or dis > 0.25:
        ver, tam = "ESPERAR", "NONE"
    elif conv >= 0.58 and dis < 0.15:
        ver, tam = "APOSTAR", "FULL" if conv >= 0.65 else "HALF"
    elif conv >= 0.52:
        ver, tam = "ESPERAR", "TACTICAL"
    else:
        ver, tam = "EVITAR", "NONE"

    return {
        "veredicto": ver,
        "apostaria": ver == "APOSTAR",
        "perspectiva_trader": (
            f"Yo {'entraría' if ver == 'APOSTAR' else 'no apostaría ahora' if ver == 'EVITAR' else 'esperaría'}: "
            f"convicción {conv:.2f}, desacuerdo {dis:.2f}. (fallback sin Gemini)"
        ),
        "confianza": int(min(conv * 100, 99)),
        "tesis": f"Convicción {conv:.2f}, desacuerdo {dis:.2f}, "
                 f"{ci.get('n_bullish', 0)}/{ci.get('n_models_active', 0)} modelos alcistas. "
                 f"Fallback sin Gemini.",
        "como_apostar": {
            "tamano": tam,
            "horizonte_d": item.get("horizonte_d", 5),
            "nota": "Ver risk_engine para entry/stop numéricos",
        },
        "evidencia_a_favor": [f"Convicción {conv:.2f}"],
        "red_flags": (["news_alerta"] if news_alerta else []),
        "incertidumbres_clave": [f"Desacuerdo σ={dis:.3f}"],
        "_fallback": True,
    }


def build_trader_prompt(item: dict, result: dict | None = None) -> str:
    """Prompt con métricas + incertidumbres para un ticker."""
    registry = (result or {}).get("model_registry", {})
    core = registry.get("core_models", [])
    active = [m["id"] for m in core if m.get("active")]
    n_core = registry.get("n_core", 4)

    slug = item.get("universe_slug", "?")
    um = ((result or {}).get("universe_metrics") or {}).get(slug, {})
    fusion = um.get("fusion", {})
    model_oos = um.get("models", {})

    oos_lines = []
    for name, md in model_oos.items():
        ci = md.get("auc_ci_90") or ["?", "?"]
        if not isinstance(ci, (list, tuple)) or len(ci) < 2:
            ci = ["?", "?"]
        oos_lines.append(
            f"    · {name}: AUC={md.get('auc')} IC90=[{ci[0]}, {ci[1]}]  "
            f"edge={md.get('edge_vs_random', 0):+.3f}"
        )
    oos_txt = "\n".join(oos_lines) or "    (métricas OOS no disponibles)"

    headlines = item.get("headlines") or []
    news_txt = "\n".join(f"    • {h}" for h in headlines[:5]) or "    (sin titulares)"
    news_sent = item.get("news_sent")
    metrics_txt = format_metrics_for_prompt(item)

    return f"""Analiza este setup de trading con los datos cuantitativos del SuperModel.

══════════════════════════════════════════════════════════
INSTRUMENTO: {item['ticker']}  |  {item.get('universe','?')} ({slug})
Moneda: {item.get('moneda','?')}  |  Precio: {item.get('precio','?')}
Ranking global: #{item.get('rank_global','?')} de {item.get('n_total','?')}
══════════════════════════════════════════════════════════

ARQUITECTURA DEL SUPER MODELO:
  · {n_core} modelos núcleo: {', '.join(active) or 'xs_lgbm, ensemble, heuristic, lstm_seq'}
  · Fusión L2: {fusion.get('selected', item.get('fusion_mode', '?'))} (stack AUC={fusion.get('stack_auc')} vs AUC-weight={fusion.get('auc_weight_auc')})

CALIDAD OOS DEL UNIVERSO (holdout 20%, IC 90% bootstrap):
{oos_txt}

MÉTRICAS E INCERTIDUMBRES — TICKER HOY:
{metrics_txt}

CONTEXTO ADICIONAL:
  Régimen: {item.get('regime','?')} (factor ×{item.get('regime_factor', 1.0)})
  Sentimiento noticias: {f'{news_sent:+.2f}' if news_sent is not None else 'n/d'}
  Titulares:
{news_txt}

PREDICCIONES RAW POR MODELO (hoy, con peso de fusión):
{chr(10).join(
    f'    · {MODEL_LABELS.get(m, m)} ({m}): score={v:.3f}  peso={item.get("model_weights", {}).get(m, 0):.3f}'
    for m, v in (item.get('signals') or {}).items()
)}

KB / LITERATURA:
  Horizontes consenso: {item.get('n_horizontes', 0)}/4
  Flags KB: {', '.join(item.get('kb_flags') or []) or '(ninguno)'}

══════════════════════════════════════════════════════════
TAREA: Simula ser el trader con book propio. ¿Apostarías TU dinero en este setup?
Considera incertidumbres (IC90 AUC, desacuerdo, régimen). Sé directo en primera persona.

Responde SOLO JSON (sin markdown):
{{
  "veredicto": "APOSTAR|ESPERAR|EVITAR",
  "apostaria": true|false,
  "perspectiva_trader": "<1-2 frases en primera persona: tu opinión honesta como trader>",
  "confianza": <0-100>,
  "tesis": "<2-3 frases: tesis de trade>",
  "como_apostar": {{
    "tamano": "FULL|HALF|TACTICAL|NONE",
    "horizonte_d": <5|10|15|20>,
    "entrada": "<limit mercado / cierre / pullbacK — descripción>",
    "gestion_riesgo": "<stop ATR, correlación, régimen>"
  }},
  "evidencia_a_favor": ["<dato numérico + LR-xxx si aplica>", "..."],
  "red_flags": ["<riesgo con incertidumbre explícita>", "..."],
  "incertidumbres_clave": ["<ej: AUC ensemble IC90 incluye 0.50>", "..."]
}}"""


def advise_ticker(
    item: dict,
    result: dict | None = None,
    client=None,
    genai_types=None,
) -> dict:
    """Un ticker → insight del trader agent."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or client is None:
        verdict = _fallback_trader(item)
        log_verdict(item["ticker"], item, verdict)
        return verdict

    try:
        prompt = build_trader_prompt(item, result)
        txt = generate_json(
            client, "trader", prompt, genai_types,
            system_instruction=TRADER_SYSTEM_PROMPT,
            max_output_tokens=900,
            temperature=0.25,
        )
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        start, end = txt.find("{"), txt.rfind("}") + 1
        if start >= 0 and end > start:
            verdict = json.loads(txt[start:end])
            verdict["_fallback"] = False
            verdict["_model"] = get_model("trader")
            if "apostaria" not in verdict:
                verdict["apostaria"] = verdict.get("veredicto") == "APOSTAR"
            log_verdict(item["ticker"], item, verdict)
            return verdict
    except Exception as e:
        logger.warning(f"Gemini trader {item['ticker']}: {e}")

    verdict = _fallback_trader(item)
    log_verdict(item["ticker"], item, verdict)
    return verdict


def advise_ranking(
    result: dict,
    tickers_map: dict[str, str] | None = None,
    top_n: int | None = None,
) -> dict:
    """
    Enriquece master_ranking con `gemini` (modo trader) en el top-N.
    """
    import time
    from src.api.gemini_analyst import fetch_news_for_ticker

    ranking = result.get("master_ranking", [])
    if not ranking:
        return result

    top_n = top_n or result.get("top_gemini", 10)
    n_total = len(ranking)
    tickers_map = tickers_map or {}

    client, genai_types = create_client()
    if client is None and os.getenv("GEMINI_API_KEY"):
        logger.warning("Gemini init failed")

    n_apostar = n_esperar = n_evitar = 0

    for item in ranking[:top_n]:
        item["n_total"] = n_total
        sym = tickers_map.get(item["ticker"], item["ticker"])
        if client is not None:
            news = fetch_news_for_ticker(
                item["ticker"], sym, item.get("universe_slug", ""))
            item["headlines"] = [
                n.get("title", "") for n in (news or []) if n and n.get("title")
            ]
        verdict = advise_ticker(item, result, client, genai_types)
        item["gemini"] = verdict
        item["gemini_agent"] = "trader"

        v = verdict.get("veredicto", "")
        n_apostar += v == "APOSTAR"
        n_esperar += v == "ESPERAR"
        n_evitar += v == "EVITAR"

        if client is not None and not verdict.get("_fallback"):
            time.sleep(1.5)

    result["gemini_summary"] = {
        "validados": min(top_n, n_total),
        "apostar": n_apostar,
        "esperar": n_esperar,
        "evitar": n_evitar,
        "modo": "trader" if client else "fallback",
        "agent": "gemini_trader",
        "model": get_model("trader"),
    }
    result["portfolio_brief"] = advise_portfolio(result, top_n=min(top_n, 10))
    return result


def _fallback_portfolio(result: dict, top_n: int = 10) -> dict:
    ranking = (result.get("master_ranking") or [])[:top_n]
    apostar, esperar, evitar = [], [], []
    allocation: dict[str, str] = {}
    incert: list[str] = []

    for item in ranking:
        t = item["ticker"]
        g = item.get("gemini") or {}
        v = g.get("veredicto", "")
        conv = float(item.get("conviction", 0))
        if v == "APOSTAR":
            apostar.append(t)
            allocation[t] = (g.get("como_apostar") or {}).get("tamano", "HALF")
        elif v in ("EVITAR", "VETA"):
            evitar.append(t)
        elif v == "ESPERAR" or v == "DEGRADA":
            esperar.append(t)
        elif conv >= 0.56 and item.get("disagreement", 1) < 0.2:
            apostar.append(t)
            allocation[t] = "HALF"
        else:
            esperar.append(t)

    reg = (result.get("universe_metrics") or {}).get("bmv", {})
    regime_p = reg.get("regime_proba") or {}
    mercado = "lateral"
    if regime_p:
        mercado = max(regime_p, key=regime_p.get)

    for slug, um in (result.get("universe_metrics") or {}).items():
        for mid, md in (um.get("models") or {}).items():
            ci = md.get("auc_ci_90") or []
            if len(ci) == 2 and ci[0] < 0.5 < ci[1]:
                incert.append(f"{slug}/{mid}: AUC IC90 cruza 0.50")

    return {
        "resumen_ejecutivo": (
            f"Top {len(ranking)} del SuperModel. "
            f"{len(apostar)} setups con convicción operativa, "
            f"{len(esperar)} en espera, {len(evitar)} a evitar. "
            "Síntesis automática (sin Gemini)."
        ),
        "mercado_hoy": mercado,
        "apostar": apostar,
        "esperar": esperar,
        "evitar": evitar,
        "allocation_sugerida": allocation,
        "riesgos_mercado": [],
        "incertidumbres_globales": incert[:5],
        "confianza_portfolio": 50,
        "_fallback": True,
    }


def build_portfolio_prompt(result: dict, top_n: int = 10) -> str:
    ranking = (result.get("master_ranking") or [])[:top_n]
    lines = []
    for item in ranking:
        g = item.get("gemini") or {}
        m = item.get("metrics") or {}
        conv_ci = (m.get("conviction") or {}).get("ci_90", [])
        lines.append(
            f"  #{item.get('rank_global')} {item['ticker']} [{item.get('universe_slug')}] "
            f"conv={item.get('conviction')} CI90={conv_ci} desac={item.get('disagreement')} "
            f"veredicto={g.get('veredicto','—')} regime={item.get('regime')}"
        )
    picks_txt = "\n".join(lines) or "  (sin picks)"

    registry = result.get("model_registry") or {}
    n_active = registry.get("n_active_total", 4)
    gs = result.get("gemini_summary") or {}

    return f"""Sintetiza una vista de PORTAFOLIO semanal long-only BMV/MX con estos picks del SuperModel.

MODELO: {n_active} predictores fusionados · agente ya validó {gs.get('validados', top_n)} tickers
Conteo trader: APOSTAR={gs.get('apostar',0)} ESPERAR={gs.get('esperar',0)} EVITAR={gs.get('evitar',0)}

TOP PICKS (con métricas):
{picks_txt}

INSIGHTS CUANTITATIVOS:
{chr(10).join('  · ' + i.get('texto','') for i in (result.get('insights') or [])[:4])}

TAREA: Como trader pro, ¿cómo armarías la semana?
- Máx 2–3 posiciones (bet_policy K=2)
- Diversificar universos si hay concentración
- Honrar incertidumbres (AUC IC90, desacuerdo)
- paper_only: usuario decide si apuesta

JSON únicamente:
{{
  "resumen_ejecutivo": "<3-4 frases para el consumidor>",
  "mercado_hoy": "alcista|lateral|bajista|mixto",
  "apostar": ["TICKER", ...],
  "esperar": ["TICKER", ...],
  "evitar": ["TICKER", ...],
  "allocation_sugerida": {{"TICKER": "FULL|HALF|TACTICAL"}},
  "riesgos_mercado": ["...", "..."],
  "incertidumbres_globales": ["...", "..."],
  "confianza_portfolio": <0-100>
}}"""


def advise_portfolio(result: dict, top_n: int = 10) -> dict:
    """Una llamada Gemini → brief de portafolio para InsightsBundle."""
    client, genai_types = create_client()
    if client is None:
        return _fallback_portfolio(result, top_n)

    try:
        prompt = build_portfolio_prompt(result, top_n)
        txt = generate_json(
            client, "trader", prompt, genai_types,
            system_instruction=TRADER_SYSTEM_PROMPT,
            max_output_tokens=700,
            temperature=0.2,
        )
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        start, end = txt.find("{"), txt.rfind("}") + 1
        if start >= 0 and end > start:
            brief = json.loads(txt[start:end])
            brief["_fallback"] = False
            brief["_model"] = get_model("trader")
            return brief
    except Exception as e:
        logger.warning(f"Gemini portfolio brief: {e}")

    return _fallback_portfolio(result, top_n)
