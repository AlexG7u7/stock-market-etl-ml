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
    # contexto enriquecido (modo agente)
    horizon_signals: dict | None = None,   # {"1s": {"rank": 2, "score": 0.71}, ...}
    macro_context:   dict | None = None,   # {"USDMXN": 1.2, "WTI": -0.5, "SP500": 0.8, "regime": "alcista"}
    n_consenso:      int = 0,
    n_universe:      int = 0,
) -> dict:
    """
    Llama a Gemini como agente analista con TODOS los outputs del modelo.
    Si no hay GEMINI_API_KEY retorna dict vacío.

    Returns:
        {
            "resumen":          str,  — tesis de inversión en 1-2 frases
            "accion":           str,  — COMPRA FUERTE / COMPRA / ESPERA / EVITA
            "confianza":        str,  — ALTA / MEDIA / BAJA
            "riesgo":           str,  — principal riesgo
            "catalizador":      str,  — qué podría potenciar el alza
            "horizonte_optimo": str,  — 1s / 2s / 3s / 4s (dónde es más fuerte)
            "sentimiento_news": str,  — positivo / neutral / negativo
            "contradiccion":    str | None  — señales contradictorias o null
        }
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    news = news or fetch_news_yfinance(sym)
    news_txt = "\n".join(f"  • {n['title']} ({n.get('ago','')})" for n in news) or "  (sin noticias recientes)"

    # ── Sección 1: señales del modelo por horizonte ───────────────────────────
    horizon_labels = {"1s": "1 semana", "2s": "2 semanas", "3s": "3 semanas", "4s": "4 semanas"}
    if horizon_signals:
        lines_hz = []
        for hk in ["1s", "2s", "3s", "4s"]:
            if hk in horizon_signals:
                h = horizon_signals[hk]
                lines_hz.append(
                    f"  • {horizon_labels[hk]}: rank #{h['rank']} / {n_universe}  |  score {h['score']:.2f}"
                )
            else:
                lines_hz.append(f"  • {horizon_labels[hk]}: NO está en top-5")
        horizons_txt = "\n".join(lines_hz)
        consenso_txt = f"Aparece en {n_consenso}/4 horizontes — {'señal de mediano plazo consistente' if n_consenso >= 3 else 'señal focalizada'}"
    else:
        horizons_txt = f"  • Rank #{rank} / {n_universe}  |  score {score:.2f}"
        consenso_txt = f"Horizonte único"

    # ── Sección 2: features técnicos rank-normalizados ─────────────────────────
    razones_txt = "\n".join(f"  - {r}" for r in razones) or "  (factores técnicos combinados)"

    # ── Sección 3: macro context ───────────────────────────────────────────────
    if macro_context:
        regime = macro_context.get("regime", "desconocido")
        macro_lines = [f"  • Régimen de mercado: {regime.upper()}"]
        for key, val in macro_context.items():
            if key == "regime":
                continue
            direction = "↑" if val > 0 else "↓"
            label = {
                "USDMXN":  "USD/MXN retorno 5d (peso)",
                "WTI":     "WTI petróleo retorno 5d",
                "SP500":   "S&P 500 retorno 5d",
                "NAFTRAC": "IPC/NAFTRAC retorno 5d",
            }.get(key, key)
            note = ""
            if key == "USDMXN" and val > 1.0:
                note = " ⚠️ peso depreciando"
            elif key == "USDMXN" and val < -1.0:
                note = " ✅ peso apreciando"
            macro_lines.append(f"  • {label}: {val:+.1f}%{direction}{note}")
        macro_txt = "\n".join(macro_lines)
    else:
        macro_txt = "  (contexto macro no disponible)"

    prompt = f"""Eres un agente analista cuantitativo de inversiones. Tienes acceso a los outputs completos del modelo predictivo para el siguiente instrumento. Sintetiza TODA la evidencia y emite una recomendación ejecutiva.

════════════════════════════════
INSTRUMENTO: {ticker}
UNIVERSO: {universe_name} ({n_universe} instrumentos analizados)
CONSENSO: {consenso_txt}
════════════════════════════════

=== SEÑALES DEL MODELO POR HORIZONTE ===
{horizons_txt}

=== FEATURES TÉCNICOS (rank-normalizados vs el universo) ===
Los features que más peso tienen en el modelo y cuál es la posición de {ticker}:
{razones_txt}

=== CONTEXTO MACRO ===
{macro_txt}

=== NOTICIAS RECIENTES ===
{news_txt}

════════════════════════════════
TAREA: Analiza la evidencia. ¿Los horizontes son consistentes? ¿El macro confirma o contradice? ¿Las noticias apoyan el momentum técnico?
════════════════════════════════

Responde SOLO en JSON con este formato exacto:
{{
  "resumen": "Tesis de inversión en 1-2 frases ejecutivas",
  "accion": "COMPRA FUERTE | COMPRA | ESPERA | EVITA",
  "confianza": "ALTA | MEDIA | BAJA",
  "riesgo": "Principal factor de riesgo en 1 frase",
  "catalizador": "Qué evento podría potenciar el alza en 1 frase",
  "horizonte_optimo": "1s | 2s | 3s | 4s",
  "sentimiento_news": "positivo | neutral | negativo",
  "contradiccion": "Describe brevemente si hay señales contradictorias entre horizontes, macro o noticias, o null si todo apunta en la misma dirección"
}}"""

    try:
        from google import genai                        # type: ignore[import]
        from google.genai import types as genai_types   # type: ignore[import]

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=512,
                temperature=0.3,
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


_CACHE_PATH = None

def _get_cache_path():
    global _CACHE_PATH
    if _CACHE_PATH is None:
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        _CACHE_PATH = root / "data" / "gemini_cache.json"
    return _CACHE_PATH


def _load_cache() -> dict:
    path = _get_cache_path()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data.get(today, {})
    except Exception:
        pass
    return {}


def _save_cache(today_cache: dict):
    path = _get_cache_path()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass
        existing[today] = today_cache
        # keep only last 7 days
        keys = sorted(existing.keys())[-7:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: existing[k] for k in keys}, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.debug(f"Cache save error: {e}")


def analyze_batch(
    picks: list[dict],
    tickers_map: dict[str, str],   # nombre_corto → símbolo yfinance
    universe_name: str,
    universe_slug: str = "",
    by_horizon: dict | None = None,    # todos los horizontes {hk: {top5: [...]}}
    macro_context: dict | None = None, # {USDMXN, WTI, SP500, regime}
    consensus: list | None = None,     # [{ticker, n_horizontes}]
    n_universe: int = 0,
) -> dict[str, dict]:
    """
    Analiza todos los picks en batch.
    Usa caché diario. Pasa contexto completo (modo agente) si está disponible.
    Retorna dict {ticker: análisis}.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    # Índice de consenso
    consensus_rank = {c["ticker"]: c["n_horizontes"] for c in (consensus or [])}

    # Señales por horizonte para cada ticker
    ticker_hz: dict[str, dict] = {}
    for hk, hdata in (by_horizon or {}).items():
        for i, p in enumerate(hdata.get("top5", []), start=1):
            t = p["ticker"]
            if t not in ticker_hz:
                ticker_hz[t] = {}
            ticker_hz[t][hk] = {"rank": i, "score": p.get("score", 0.5)}

    today_cache = _load_cache()
    results = {}

    for p in picks:
        name = p["ticker"]
        sym  = tickers_map.get(name, name)

        # Cache key: incluye fecha implícita en _load_cache
        if name in today_cache:
            # Solo usar caché si tiene los campos del modo agente
            if today_cache[name].get("confianza"):
                logger.info(f"  Gemini {name}: cache hit ✓")
                results[name] = today_cache[name]
                continue

        news   = fetch_news_for_ticker(name, sym, universe_slug)
        result = analyze_ticker(
            ticker=name,
            sym=sym,
            rank=p.get("rank", 1),
            score=p.get("score", 0.5),
            razones=p.get("razones", []),
            universe_name=universe_name,
            news=news,
            horizon_signals=ticker_hz.get(name),
            macro_context=macro_context,
            n_consenso=consensus_rank.get(name, 0),
            n_universe=n_universe,
        )
        enriched = {**result, "noticias": news}
        results[name] = enriched

        if result:
            today_cache[name] = enriched
            _save_cache(today_cache)

        logger.info(f"  Gemini {name}: {result.get('accion','—')} ({result.get('confianza','')}) — {result.get('resumen','')[:60]}...")

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
