"""
Gemini Analyst — análisis ejecutivo por ticker.

Para cada pick del top-5, llama a Gemini con:
  - Score del modelo + razones técnicas
  - Noticias recientes del ticker (yfinance)
  - Contexto de mercado

Retorna un análisis ejecutivo accionable: qué comprar, por qué, y qué
riesgo tener en cuenta. Mismo patrón que TrabajadoresDomesticos.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ─── Fetch noticias por ticker (yfinance — gratis, sin key) ──────────────────

def fetch_news_yfinance(sym: str, max_items: int = 5) -> list[dict]:
    """
    Obtiene noticias recientes de yfinance para cualquier símbolo.
    Funciona para: acciones USA, ETFs, cripto-proxy, y .MX símbolos.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        news = getattr(ticker, "news", None) or []
        out = []
        for n in news[:max_items]:
            title = n.get("title") or n.get("content", {}).get("title", "")
            if title:
                out.append({
                    "title": title,
                    "publisher": n.get("publisher") or n.get("content", {}).get("provider", {}).get("displayName", ""),
                    "link": n.get("link") or n.get("content", {}).get("canonicalUrl", {}).get("url", ""),
                    "ago": _ago(n.get("providerPublishTime")),
                })
        return out
    except Exception as e:
        logger.debug(f"yfinance news {sym}: {e}")
        return []


def _ago(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(ts)
        diff = datetime.now() - dt
        if diff.days > 0:
            return f"hace {diff.days}d"
        hours = diff.seconds // 3600
        return f"hace {hours}h" if hours > 0 else "reciente"
    except Exception:
        return ""


# ─── Análisis ejecutivo por ticker con Gemini ─────────────────────────────────

def analyze_ticker(
    ticker: str,
    sym: str,
    rank: int,
    score: float,
    razones: list[str],
    universe_name: str,
    news: list[dict] | None = None,
) -> dict:
    """
    Llama a Gemini 2.5-flash para generar un análisis ejecutivo del ticker.
    Si no hay GEMINI_API_KEY, retorna dict vacío (degradación elegante).

    Returns:
        {
            "resumen": str,       — 1 frase ejecutiva de por qué está en el top
            "accion": str,        — "COMPRA FUERTE / COMPRA / ESPERA / EVITA"
            "riesgo": str,        — principal riesgo en 1 frase
            "catalizador": str,   — qué podría hacer que suba más
            "sentimiento_news": str  — positivo/neutral/negativo según noticias
        }
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    news = news or fetch_news_yfinance(sym)
    news_txt = "\n".join(f"  • {n['title']} ({n.get('ago','')})" for n in news) or "  (sin noticias recientes)"
    razones_txt = "\n".join(f"  - {r}" for r in razones) or "  (múltiples factores técnicos)"

    prompt = f"""Eres un analista de inversiones ejecutivo. Analiza este instrumento:

Instrumento: {ticker}
Universo: {universe_name}
Rank del modelo: #{rank} de su universo (top-5)
Score del modelo: {score:.2f} (mayor = mejor momentum relativo)

Señales técnicas que lo pusieron en el top:
{razones_txt}

Noticias recientes:
{news_txt}

Responde SOLO en JSON con este formato exacto:
{{
  "resumen": "Una frase ejecutiva de por qué este instrumento está en el top ahora",
  "accion": "COMPRA FUERTE | COMPRA | ESPERA | EVITA",
  "riesgo": "Una frase sobre el principal riesgo",
  "catalizador": "Una frase sobre qué podría potenciar el alza",
  "sentimiento_news": "positivo | neutral | negativo"
}}"""

    try:
        from google import genai                        # type: ignore[import]
        from google.genai import types as genai_types   # type: ignore[import]

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=512,
                temperature=0.3,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        txt = (response.text or "").strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        start = txt.find("{")
        end   = txt.rfind("}") + 1
        return json.loads(txt[start:end]) if start >= 0 and end > start else {}
    except Exception as e:
        logger.warning(f"Gemini analyze_ticker {ticker}: {e}")
        return {}


def analyze_batch(
    picks: list[dict],
    tickers_map: dict[str, str],   # nombre_corto → símbolo yfinance
    universe_name: str,
) -> dict[str, dict]:
    """
    Analiza todos los picks del top-5 en batch.
    Retorna dict {ticker: análisis}.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    results = {}
    for p in picks:
        name   = p["ticker"]
        sym    = tickers_map.get(name, name)
        news   = fetch_news_yfinance(sym)
        result = analyze_ticker(
            ticker=name,
            sym=sym,
            rank=p.get("rank", 1),
            score=p.get("score", 0.5),
            razones=p.get("razones", []),
            universe_name=universe_name,
            news=news,
        )
        results[name] = {**result, "noticias": news}
        logger.info(f"  Gemini {name}: {result.get('accion','—')} — {result.get('resumen','')[:60]}...")

    return results


# ─── Fuentes de noticias por clase de activo ──────────────────────────────────

NEWS_SOURCES = {
    "🇲🇽 Acciones BMV": {
        "fuentes": [
            {"nombre": "DataBursátil",  "tipo": "API",  "costo": "Incluida", "url": "https://databursatil.com/docs.html",     "cobertura": "Noticias BMV en tiempo real, cables financieros MX"},
            {"nombre": "El Financiero", "tipo": "RSS",  "costo": "Gratis",   "url": "https://www.elfinanciero.com.mx/rss",    "cobertura": "Economía y finanzas México"},
            {"nombre": "El Economista", "tipo": "RSS",  "costo": "Gratis",   "url": "https://www.eleconomista.com.mx/rss",   "cobertura": "Mercados mexicanos"},
            {"nombre": "yfinance news", "tipo": "SDK",  "costo": "Gratis",   "url": "https://pypi.org/project/yfinance/",    "cobertura": "Noticias por ticker .MX"},
        ],
        "integrado": ["DataBursátil", "yfinance news"],
    },
    "🇺🇸 Acciones USA (SIC)": {
        "fuentes": [
            {"nombre": "yfinance news",   "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",          "cobertura": "Noticias por ticker NYSE/Nasdaq"},
            {"nombre": "Alpha Vantage",   "tipo": "API",  "costo": "Gratis 25/d", "url": "https://www.alphavantage.co/",                "cobertura": "News + sentimiento para acciones USA"},
            {"nombre": "Polygon.io",      "tipo": "API",  "costo": "Gratis 5/min","url": "https://polygon.io/docs/stocks/get_v2_reference_news", "cobertura": "Noticias + earnings USA"},
            {"nombre": "Reuters RSS",     "tipo": "RSS",  "costo": "Gratis",      "url": "https://feeds.reuters.com/reuters/businessNews", "cobertura": "Negocios y finanzas globales"},
        ],
        "integrado": ["yfinance news"],
    },
    "📦 ETFs": {
        "fuentes": [
            {"nombre": "yfinance news",  "tipo": "SDK",  "costo": "Gratis",   "url": "https://pypi.org/project/yfinance/",        "cobertura": "Noticias por ETF (SPY, QQQ, etc.)"},
            {"nombre": "ETF.com RSS",    "tipo": "RSS",  "costo": "Gratis",   "url": "https://www.etf.com/rss",                   "cobertura": "Flujos de capital en ETFs"},
            {"nombre": "Seeking Alpha",  "tipo": "API",  "costo": "$29/mes",  "url": "https://seekingalpha.com/api/v3/articles",  "cobertura": "Análisis de ETFs con IA"},
        ],
        "integrado": ["yfinance news"],
    },
    "₿ Cripto (proxies GBM)": {
        "fuentes": [
            {"nombre": "CryptoPanic",     "tipo": "API",  "costo": "Gratis 1k/mes","url": "https://cryptopanic.com/developers/api/",   "cobertura": "Noticias cripto con sentimiento por coin"},
            {"nombre": "CoinGecko",       "tipo": "API",  "costo": "Gratis 30/min","url": "https://www.coingecko.com/api/v3",           "cobertura": "Precios + noticias cripto globales"},
            {"nombre": "yfinance news",   "tipo": "SDK",  "costo": "Gratis",       "url": "https://pypi.org/project/yfinance/",         "cobertura": "Noticias de IBIT, MSTR, COIN"},
            {"nombre": "Decrypt RSS",     "tipo": "RSS",  "costo": "Gratis",       "url": "https://decrypt.co/feed",                    "cobertura": "Noticias BTC/ETH en tiempo real"},
        ],
        "integrado": ["yfinance news"],
        "proximos": ["CryptoPanic"],
    },
    "🏢 FIBRAs (bienes raíces MX)": {
        "fuentes": [
            {"nombre": "DataBursátil",    "tipo": "API",  "costo": "Incluida",  "url": "https://databursatil.com/docs.html",          "cobertura": "Noticias FIBRAs en tiempo real"},
            {"nombre": "AMEFIBRA",        "tipo": "Web",  "costo": "Gratis",    "url": "https://amefibra.com/noticias/",               "cobertura": "Reportes trimestrales FIBRA"},
            {"nombre": "yfinance news",   "tipo": "SDK",  "costo": "Gratis",    "url": "https://pypi.org/project/yfinance/",           "cobertura": "Noticias de FIBRAs listadas"},
        ],
        "integrado": ["DataBursátil", "yfinance news"],
    },
}
