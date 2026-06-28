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
                    "fuente": "Yahoo Finance",
                })
        return out
    except Exception as e:
        logger.debug(f"yfinance news {sym}: {e}")
        return []


# ─── Fetch noticias de DataBursátil (BMV — español, general de mercado) ───────

def fetch_news_databursatil(ticker_mx: str, max_items: int = 5) -> list[dict]:
    """
    Obtiene noticias de DataBursátil para el mercado mexicano.
    La API devuelve noticias generales (no filtra por emisora individual),
    así que filtramos las que mencionan el ticker en el título.
    Requiere DATABURSATIL_API_TOKEN.
    """
    token = os.getenv("DATABURSATIL_API_TOKEN")
    if not token:
        return []
    try:
        import requests
        resp = requests.get(
            "https://api.databursatil.com/v2/cables",
            params={"token": token, "categorias": "top,generales,flash"},
            timeout=8,
        )
        if not resp.ok:
            return []
        data = resp.json()
        out  = []
        # Intentar filtrar por ticker; si no hay resultados, devolver las top
        ticker_upper = ticker_mx.upper()
        all_news = []
        for cat, items in (data.items() if isinstance(data, dict) else []):
            for it in (items if isinstance(items, list) else []):
                title = it.get("titulo") or it.get("t") or it.get("headline") or ""
                if title:
                    all_news.append({
                        "title":     title,
                        "publisher": "DataBursátil",
                        "link":      it.get("url") or "",
                        "ago":       it.get("fecha") or "",
                        "fuente":    "DataBursátil",
                        "_relevante": ticker_upper in title.upper(),
                    })
        # Primero las que mencionan el ticker, luego las generales
        relevantes = [n for n in all_news if n.get("_relevante")]
        generales  = [n for n in all_news if not n.get("_relevante")]
        combined   = (relevantes + generales)[:max_items]
        for n in combined:
            n.pop("_relevante", None)
        return combined
    except Exception as e:
        logger.debug(f"DataBursátil news {ticker_mx}: {e}")
        return []


# ─── Fetch noticias de CryptoPanic (cripto — requiere key) ────────────────────

_CRYPTO_SYMBOL_MAP = {
    "IBIT": "BTC", "FBTC": "BTC", "GBTC": "BTC",
    "ETHA": "ETH",
    "MSTR": "BTC", "COIN": "COIN", "MARA": "BTC", "RIOT": "BTC", "CLSK": "BTC",
}

def fetch_news_cryptopanic(ticker: str, max_items: int = 5) -> list[dict]:
    """
    Obtiene noticias de CryptoPanic para el activo cripto subyacente.
    Requiere CRYPTOPANIC_API_KEY (registro gratuito en cryptopanic.com).
    Sin key retorna [] para usar yfinance como fallback.
    """
    api_key = os.getenv("CRYPTOPANIC_API_KEY")
    if not api_key:
        return []
    currency = _CRYPTO_SYMBOL_MAP.get(ticker, "BTC")
    try:
        import requests
        resp = requests.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={"auth_token": api_key, "currencies": currency, "kind": "news"},
            timeout=8,
        )
        if not resp.ok:
            return []
        posts = resp.json().get("results", [])
        out = []
        for p in posts[:max_items]:
            title = p.get("title", "")
            if title:
                out.append({
                    "title":     title,
                    "publisher": p.get("source", {}).get("title", "CryptoPanic"),
                    "link":      p.get("url", ""),
                    "ago":       "",
                    "fuente":    "CryptoPanic",
                })
        return out
    except Exception as e:
        logger.debug(f"CryptoPanic {ticker}: {e}")
        return []


# ─── Fetch noticias de Google News RSS (gratis, sin key) ─────────────────────

def fetch_news_google_rss(query: str, max_items: int = 5, lang: str = "es") -> list[dict]:
    """
    Google News RSS — gratis, sin key, cualquier query.
    query: ej. "WALMEX BMV" o "Bitcoin ETF"
    """
    try:
        import urllib.parse, xml.etree.ElementTree as ET
        hl = "es-419" if lang == "es" else "en-US"
        gl = "MX"     if lang == "es" else "US"
        q  = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
        import requests as _req
        r = _req.get(url, timeout=8,
                     headers={"User-Agent": "Mozilla/5.0 (compatible; stockbot/1.0)"})
        if not r.ok:
            return []
        root = ET.fromstring(r.content)
        out  = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            link  = item.findtext("link",  "")
            pub   = item.findtext("pubDate", "")
            if title:
                out.append({
                    "title":     title,
                    "publisher": "Google News",
                    "link":      link,
                    "ago":       pub[:16] if pub else "",
                    "fuente":    "Google News RSS",
                })
        return out
    except Exception as e:
        logger.debug(f"Google News RSS '{query}': {e}")
        return []


# ─── Fetch noticias de Alpha Vantage (25 req/día gratis, sentimiento incluido) 

def fetch_news_alpha_vantage(ticker: str, max_items: int = 5) -> list[dict]:
    """
    Alpha Vantage News & Sentiment API.
    Requiere ALPHA_VANTAGE_API_KEY (gratis en alphavantage.co).
    Incluye sentimiento por artículo (bullish/bearish score).
    Límite: 25 req/día en plan gratuito.
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return []
    try:
        import requests
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers":  ticker,
                "apikey":   api_key,
                "limit":    max_items,
                "sort":     "LATEST",
            },
            timeout=10,
        )
        if not r.ok:
            return []
        feed = r.json().get("feed", [])
        out  = []
        for item in feed[:max_items]:
            title = item.get("title", "")
            if not title:
                continue
            # sentiment_label: Bullish / Bearish / Neutral
            sent  = item.get("overall_sentiment_label", "")
            score = item.get("overall_sentiment_score", "")
            sent_icon = {"Bullish": "📈", "Bearish": "📉", "Neutral": "➡️"}.get(sent, "")
            out.append({
                "title":     f"{sent_icon} {title}" if sent_icon else title,
                "publisher": item.get("source", "Alpha Vantage"),
                "link":      item.get("url", ""),
                "ago":       item.get("time_published", "")[:10],
                "fuente":    "Alpha Vantage",
                "sentiment": sent,
                "score":     score,
            })
        return out
    except Exception as e:
        logger.debug(f"Alpha Vantage {ticker}: {e}")
        return []

def fetch_news_for_ticker(
    ticker: str,
    sym: str,
    universe_slug: str,
    max_items: int = 5,
) -> list[dict]:
    """
    Prioridad por universo:
      bmv/fibras → DataBursátil → Alpha Vantage → Google News RSS (español)
      cripto     → CryptoPanic  → Alpha Vantage → yfinance
      usa/etfs   → Alpha Vantage → yfinance → Google News RSS
    """
    if universe_slug in ("bmv", "fibras"):
        news = fetch_news_databursatil(ticker, max_items)
        if not news:
            news = fetch_news_alpha_vantage(ticker, max_items)
        if not news:
            news = fetch_news_google_rss(f"{ticker} BMV bolsa mexicana", max_items, lang="es")
        return news

    if universe_slug == "cripto":
        news = fetch_news_cryptopanic(ticker, max_items)
        if not news:
            news = fetch_news_alpha_vantage(ticker, max_items)
        if not news:
            news = fetch_news_yfinance(sym, max_items)
        return news

    # usa / etfs → Alpha Vantage (tiene sentimiento), luego yfinance
    news = fetch_news_alpha_vantage(ticker, max_items)
    if not news:
        news = fetch_news_yfinance(sym, max_items)
    return news


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
    universe_slug: str = "",
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
        news   = fetch_news_for_ticker(name, sym, universe_slug)
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
            {"nombre": "DataBursátil",  "tipo": "API",  "costo": "Incluida",    "url": "https://databursatil.com/docs.html",     "cobertura": "Cables BMV en español, mercado MX del día"},
            {"nombre": "Alpha Vantage", "tipo": "API",  "costo": "Gratis 25/d", "url": "https://alphavantage.co",                "cobertura": "Noticias + sentimiento (Bullish/Bearish) para tickers"},
            {"nombre": "Google News",   "tipo": "RSS",  "costo": "Gratis",      "url": "https://news.google.com/rss",            "cobertura": "Búsqueda en español de cualquier ticker/empresa"},
            {"nombre": "BIVA RSS",      "tipo": "RSS",  "costo": "Gratis",      "url": "https://www.biva.mx/cms/.../rss",        "cobertura": "Hechos relevantes y avisos oficiales de emisoras"},
            {"nombre": "yfinance",      "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",     "cobertura": "Noticias Yahoo Finance (fallback)"},
        ],
        "integrado": ["DataBursátil", "Alpha Vantage", "Google News", "yfinance"],
    },
    "🇺🇸 Acciones USA (SIC)": {
        "fuentes": [
            {"nombre": "Alpha Vantage", "tipo": "API",  "costo": "Gratis 25/d", "url": "https://alphavantage.co",                            "cobertura": "Noticias + sentimiento Bullish/Bearish para NYSE/Nasdaq"},
            {"nombre": "yfinance",      "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",                  "cobertura": "Yahoo Finance news por ticker"},
            {"nombre": "Polygon.io",    "tipo": "API",  "costo": "Gratis 5/min","url": "https://polygon.io/docs/stocks/get_v2_reference_news", "cobertura": "Noticias + earnings USA, tiempo real"},
            {"nombre": "Google News",   "tipo": "RSS",  "costo": "Gratis",      "url": "https://news.google.com/rss",                         "cobertura": "Cualquier ticker en inglés"},
        ],
        "integrado": ["Alpha Vantage", "yfinance"],
        "proximos":  ["Polygon.io"],
    },
    "📦 ETFs": {
        "fuentes": [
            {"nombre": "Alpha Vantage", "tipo": "API",  "costo": "Gratis 25/d", "url": "https://alphavantage.co",               "cobertura": "Noticias + sentimiento para ETFs (SPY, QQQ, GLD...)"},
            {"nombre": "yfinance",      "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",     "cobertura": "Yahoo Finance news por ETF"},
            {"nombre": "ETF.com RSS",   "tipo": "RSS",  "costo": "Gratis",      "url": "https://www.etf.com/rss",                "cobertura": "Flujos de capital y análisis de ETFs"},
        ],
        "integrado": ["Alpha Vantage", "yfinance"],
    },
    "₿ Cripto (proxies GBM)": {
        "fuentes": [
            {"nombre": "CryptoPanic",   "tipo": "API",  "costo": "Gratis c/key","url": "https://cryptopanic.com/developers/api/",   "cobertura": "Noticias BTC/ETH con sentimiento, 1k req/mes gratis"},
            {"nombre": "Alpha Vantage", "tipo": "API",  "costo": "Gratis 25/d", "url": "https://alphavantage.co",                   "cobertura": "Noticias IBIT, MSTR, COIN con sentimiento"},
            {"nombre": "yfinance",      "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",         "cobertura": "Yahoo Finance (fallback)"},
            {"nombre": "Decrypt RSS",   "tipo": "RSS",  "costo": "Gratis",      "url": "https://decrypt.co/feed",                    "cobertura": "Noticias BTC/ETH en tiempo real"},
        ],
        "integrado": ["CryptoPanic", "Alpha Vantage", "yfinance"],
    },
    "🏢 FIBRAs (bienes raíces MX)": {
        "fuentes": [
            {"nombre": "DataBursátil",  "tipo": "API",  "costo": "Incluida",    "url": "https://databursatil.com/docs.html",     "cobertura": "Cables BMV en español (FIBRAs incluidas)"},
            {"nombre": "Google News",   "tipo": "RSS",  "costo": "Gratis",      "url": "https://news.google.com/rss",            "cobertura": "Noticias FUNO, FIBRAPL, TERRA en español"},
            {"nombre": "yfinance",      "tipo": "SDK",  "costo": "Gratis",      "url": "https://pypi.org/project/yfinance/",     "cobertura": "Yahoo Finance (fallback)"},
        ],
        "integrado": ["DataBursátil", "Alpha Vantage", "Google News", "yfinance"],
    },
}
