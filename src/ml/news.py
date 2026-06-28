"""
Módulo de noticias financieras — scraping + NLP sentiment + features.

Fuentes (en orden de prioridad):
  1. Yahoo Finance  — últimos ~30 artículos por ticker (yfinance .news)
  2. Google News RSS — búsqueda por ticker/empresa, muy fresco
  3. El Financiero RSS — noticias BMV en español
  4. Expansión RSS   — mercados MX en español
  5. GDELT Project   — historial desde 2015 (para backfill de entrenamiento)

Sentiment:
  - Primario: Gemini 2.5-flash via google-genai (si GEMINI_API_KEY está disponible)
  - Fallback: scoring por keywords en español + inglés (siempre disponible)

Features generadas por ticker:
  news_sent_score   — sentimiento promedio últimos N días  [-1, +1]
  news_count_7d     — log(1 + n_artículos)
  news_sent_delta   — cambio de sentimiento vs ventana anterior
  news_sent_vol     — std de sentimientos (incertidumbre)

Uso rápido:
  from src.ml.news import get_news_features, batch_news_features

  feat = get_news_features("ALSEA", "ALSEA.MX", "Alsea restaurantes Mexico", days_back=7)
  df   = batch_news_features(tickers_dict, days_back=7)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

ROOT     = Path(__file__).parent.parent.parent
NEWS_DIR = ROOT / "data" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

# ── Timeouts y límites ────────────────────────────────────────────────────────
REQUEST_TIMEOUT  = 10   # segundos por request HTTP
MAX_ARTICLES     = 30   # máx artículos por fuente por ticker
GEMINI_BATCH     = 20   # artículos por llamada a Gemini
RATE_LIMIT_SLEEP = 0.3  # segundos entre requests RSS

# ── Keywords para scoring de fallback ────────────────────────────────────────
_POS_KEYWORDS = {
    # Español
    "subida","alza","sube","gana","ganancias","beneficio","crecimiento","record",
    "máximo","supera","mejora","positivo","dividend","dividendo","compra","acumula",
    "expansión","récord","fortalece","impulsa","optimista","aumento","avanza",
    # Inglés
    "surge","rises","gains","profit","record","beats","growth","buy","upgrade",
    "positive","strong","rally","outperform","bullish","increase","boost",
}
_NEG_KEYWORDS = {
    # Español
    "caída","baja","cae","pérdida","pierde","quiebra","fraude","vende","retrocede",
    "riesgo","incertidumbre","cierre","multa","demanda","recorte","negativo","alerta",
    "preocupa","debilita","contracción","crisis","presión","decepción",
    # Inglés
    "falls","drops","loses","loss","decline","risk","fraud","sell","downgrade",
    "negative","weak","bearish","cut","miss","concern","warning","lawsuit","bankruptcy",
}


# ── Dataclass de artículo ─────────────────────────────────────────────────────

@dataclass
class Article:
    ticker:       str
    title:        str
    summary:      str
    url:          str
    published_ts: int    # Unix timestamp UTC
    source:       str
    sentiment:    float = 0.0   # −1 a +1, se rellena después

    @property
    def published_dt(self) -> datetime:
        return datetime.fromtimestamp(self.published_ts, tz=timezone.utc)

    def is_within(self, days: int) -> bool:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        return self.published_dt >= cutoff

    def text(self) -> str:
        return f"{self.title}. {self.summary}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yfinance(yf_symbol: str, ticker: str) -> list[Article]:
    """Descarga noticias via yfinance .news (últimas ~30 noticias)."""
    try:
        items = yf.Ticker(yf_symbol).news or []
        articles = []
        for item in items[:MAX_ARTICLES]:
            ts = item.get("providerPublishTime") or item.get("publisher_time", 0)
            articles.append(Article(
                ticker       = ticker,
                title        = item.get("title", ""),
                summary      = item.get("summary", "") or item.get("description", ""),
                url          = item.get("link", "") or item.get("url", ""),
                published_ts = int(ts) if ts else 0,
                source       = "yfinance",
            ))
        return [a for a in articles if a.published_ts > 0]
    except Exception as e:
        logger.debug(f"yfinance news {yf_symbol}: {e}")
        return []


def _parse_rss_feed(url: str, ticker: str, source: str,
                    keyword_filter: Optional[str] = None) -> list[Article]:
    """Helper genérico para parsear feeds RSS."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        articles = []

        # RSS 2.0
        for item in root.iter("item"):
            title   = item.findtext("title", "")
            summary = item.findtext("description", "") or item.findtext("summary", "")
            link    = item.findtext("link", "")
            pub_raw = item.findtext("pubDate", "")

            if keyword_filter and keyword_filter.lower() not in (title + summary).lower():
                continue

            # parsear fecha
            ts = 0
            if pub_raw:
                try:
                    from email.utils import parsedate_to_datetime
                    ts = int(parsedate_to_datetime(pub_raw).timestamp())
                except Exception:
                    pass

            if title:
                articles.append(Article(
                    ticker=ticker, title=title,
                    summary=_strip_html(summary or ""),
                    url=link, published_ts=ts, source=source,
                ))

        return articles[:MAX_ARTICLES]
    except Exception as e:
        logger.debug(f"RSS {url}: {e}")
        return []


def _strip_html(text: str) -> str:
    """Elimina tags HTML básicos."""
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


def fetch_google_news_rss(query: str, ticker: str, lang: str = "es-MX") -> list[Article]:
    """
    Busca en Google News RSS.
    query: texto de búsqueda, e.g. "ALSEA BMV Mexico"
    """
    encoded = requests.utils.quote(query)
    region  = "MX" if "MX" in lang.upper() else "US"
    ceid    = f"{region}:{lang.split('-')[0]}"
    url     = (f"https://news.google.com/rss/search"
               f"?q={encoded}&hl={lang}&gl={region}&ceid={ceid}")
    time.sleep(RATE_LIMIT_SLEEP)
    return _parse_rss_feed(url, ticker, "google_news")


def fetch_elfinanciero_rss(ticker: str, keyword: str) -> list[Article]:
    """Parsea El Financiero RSS filtrando por keyword (nombre empresa/ticker)."""
    feeds = [
        "https://www.elfinanciero.com.mx/rss/mercados.xml",
        "https://www.elfinanciero.com.mx/rss/economia.xml",
    ]
    articles = []
    for feed_url in feeds:
        articles += _parse_rss_feed(feed_url, ticker, "elfinanciero", keyword_filter=keyword)
        time.sleep(RATE_LIMIT_SLEEP)
    return articles[:MAX_ARTICLES]


def fetch_expansion_rss(ticker: str, keyword: str) -> list[Article]:
    """Parsea Expansión RSS filtrando por keyword."""
    feeds = [
        "https://expansion.mx/rss/empresas",
        "https://expansion.mx/rss/mercados",
    ]
    articles = []
    for feed_url in feeds:
        articles += _parse_rss_feed(feed_url, ticker, "expansion", keyword_filter=keyword)
        time.sleep(RATE_LIMIT_SLEEP)
    return articles[:MAX_ARTICLES]


def fetch_gdelt(query: str, ticker: str, days_back: int = 7) -> list[Article]:
    """
    GDELT Project — historial hasta 2015.
    Ideal para backfill de datos de entrenamiento.
    query: e.g. "ALSEA Mexico BMV"
    """
    try:
        timespan = f"{days_back}d"
        encoded  = requests.utils.quote(query)
        url = (f"https://api.gdeltproject.org/api/v2/doc/doc"
               f"?query={encoded}&mode=artlist&maxrecords={MAX_ARTICLES}"
               f"&format=json&timespan={timespan}&sourcelang=spanish+english")
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data     = resp.json()
        articles_raw = data.get("articles") or []
        articles = []
        for art in articles_raw:
            title   = art.get("title", "")
            url_art = art.get("url", "")
            seen    = art.get("seendate", "")  # e.g. "20240628T143000Z"
            ts      = 0
            if seen:
                try:
                    dt = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                except Exception:
                    pass
            if title:
                articles.append(Article(
                    ticker=ticker, title=title, summary="",
                    url=url_art, published_ts=ts, source="gdelt",
                ))
        return articles
    except Exception as e:
        logger.debug(f"GDELT {query}: {e}")
        return []


def fetch_cryptopanic(ticker: str, currency: str = "BTC") -> list[Article]:
    """CryptoPanic API — noticias cripto (requiere CRYPTOPANIC_API_KEY)."""
    api_key = os.environ.get("CRYPTOPANIC_API_KEY")
    if not api_key:
        return []
    try:
        url  = f"https://cryptopanic.com/api/v1/posts/?auth_token={api_key}&currencies={currency}&public=true"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        articles = []
        for post in (data.get("results") or [])[:MAX_ARTICLES]:
            ts = 0
            pub = post.get("published_at", "")
            if pub:
                try:
                    dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                except Exception:
                    pass
            articles.append(Article(
                ticker=ticker,
                title=post.get("title", ""),
                summary=post.get("body") or "",
                url=post.get("url", ""),
                published_ts=ts,
                source="cryptopanic",
            ))
        return articles
    except Exception as e:
        logger.debug(f"CryptoPanic {currency}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────

def _score_keywords(text: str) -> float:
    """
    Scoring simple por keywords.
    Retorna float en [−1, +1].
    """
    tokens = set(text.lower().split())
    pos = len(tokens & _POS_KEYWORDS)
    neg = len(tokens & _NEG_KEYWORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def score_with_gemini(articles: list[Article], company_name: str) -> list[Article]:
    """
    Asigna sentimiento a cada artículo.
    Siempre usa keyword scoring (instante, sin cuota).
    Llama a Gemini solo si GEMINI_NEWS_ENABLED=true en el entorno.
    """
    # Keyword scoring siempre (rápido, sin cuota)
    for a in articles:
        a.sentiment = _score_keywords(a.text())

    # Gemini opcional — activar con GEMINI_NEWS_ENABLED=true
    if os.environ.get("GEMINI_NEWS_ENABLED", "").lower() != "true":
        return articles

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not articles:
        return articles

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        for i in range(0, len(articles), GEMINI_BATCH):
            batch = articles[i : i + GEMINI_BATCH]
            headlines = "\n".join(f"{j+1}. {a.title}" for j, a in enumerate(batch))
            prompt = f"""Eres un analista financiero. Analiza el sentimiento de cada titular
respecto a "{company_name}".
Scores: +1.0=muy positivo, +0.5=positivo, 0.0=neutral, -0.5=negativo, -1.0=muy negativo
Responde SOLO con JSON: {{"1": score, "2": score, ...}}

Titulares:
{headlines}"""

            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    max_output_tokens=256, temperature=0.1,
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = (resp.text or "").strip()
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start >= 0 and end > start:
                scores_map = json.loads(text[start:end])
                for j, art in enumerate(batch):
                    key = str(j + 1)
                    if key in scores_map:
                        try:
                            art.sentiment = float(scores_map[key])
                        except (ValueError, TypeError):
                            pass  # mantener keyword score
            time.sleep(1.5)

    except Exception as e:
        logger.debug(f"Gemini sentiment: {e} — usando keyword scores")

    return articles


def batch_score_gemini(
    tickers_articles: dict[str, list[Article]],
    top_n_headlines: int = 3,
) -> dict[str, float]:
    """
    Calcula sentimiento promedio para múltiples tickers en UNA sola llamada a Gemini.
    Más eficiente que llamar por ticker (ahorra cuota de API).

    Retorna dict ticker → sent_score promedio.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {}

    # Construir resumen compacto: ticker → top-N headlines
    ticker_headlines: dict[str, list[str]] = {}
    for ticker, arts in tickers_articles.items():
        headlines = [a.title for a in arts if a.title][:top_n_headlines]
        if headlines:
            ticker_headlines[ticker] = headlines

    if not ticker_headlines:
        return {}

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        # Un solo prompt con todos los tickers
        lines = []
        for ticker, hs in ticker_headlines.items():
            joined = " | ".join(hs)
            lines.append(f"{ticker}: {joined}")
        content = "\n".join(lines)

        prompt = f"""Eres un analista financiero senior. Para cada empresa asigna un score
de sentimiento basado en sus noticias recientes:
  +1.0 = muy positivo · 0.0 = neutral · -1.0 = muy negativo

Responde SOLO con JSON: {{"TICKER": score, ...}}

Noticias:
{content}"""

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=512, temperature=0.1,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (resp.text or "").strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return {k: float(v) for k, v in json.loads(text[start:end]).items()}

    except Exception as e:
        logger.debug(f"batch_score_gemini: {e}")

    return {}


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def _compute_features_from_articles(
    articles: list[Article],
    days_back: int = 7,
) -> dict[str, float]:
    """
    Calcula las 4 features de noticias a partir de una lista de artículos
    con .sentiment ya asignado.
    """
    now     = datetime.now(tz=timezone.utc)
    cutoff  = now - timedelta(days=days_back)
    cutoff2 = now - timedelta(days=days_back * 2)

    recent  = [a for a in articles if a.published_dt >= cutoff]
    prior   = [a for a in articles if cutoff2 <= a.published_dt < cutoff]

    sent_recent = [a.sentiment for a in recent] or [0.0]
    sent_prior  = [a.sentiment for a in prior]  or [0.0]

    sent_score  = float(np.mean(sent_recent))
    sent_prior_mean = float(np.mean(sent_prior))
    sent_vol    = float(np.std(sent_recent)) if len(sent_recent) > 1 else 0.0
    count_7d    = float(np.log1p(len(recent)))
    sent_delta  = round(sent_score - sent_prior_mean, 4)

    return {
        "news_sent_score":  round(sent_score, 4),
        "news_count_7d":    round(count_7d, 4),
        "news_sent_delta":  round(sent_delta, 4),
        "news_sent_vol":    round(sent_vol, 4),
        "n_articles":       len(recent),
        "sources":          list({a.source for a in recent}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

# Mapa de ticker → query para búsqueda (optimizado por universo)
_SEARCH_QUERIES: dict[str, tuple[str, str]] = {
    # (google_query, keyword_para_rss_mx)
    # BMV — búsqueda en español enfocada en BMV
    "ALSEA":    ("Alsea restaurantes BMV Mexico", "Alsea"),
    "WALMEX":   ("Walmex Walmart Mexico BMV", "Walmex"),
    "FEMSAUBD": ("FEMSA Coca-Cola Mexico BMV", "FEMSA"),
    "GMEXICOB": ("Grupo Mexico mineria BMV", "Grupo Mexico"),
    "CEMEXCPO": ("Cemex cemento Mexico BMV", "Cemex"),
    "GFNORTEO": ("GFNorte Banorte banco Mexico BMV", "Banorte"),
    "BIMBOA":   ("Bimbo alimentos Mexico BMV", "Bimbo"),
    "KIMBERA":  ("Kimberly Clark Mexico BMV", "Kimberly"),
    "PINFRA":   ("Pinfra autopistas Mexico BMV", "Pinfra"),
    "ORBIA":    ("Orbia Mexichem Mexico BMV", "Orbia"),
    "GRUMAB":   ("Gruma maiz tortilla Mexico BMV", "Gruma"),
    "ASURB":    ("Asur aeropuertos sureste Mexico BMV", "Asur"),
    "OMAB":     ("OMA aeropuertos Mexico BMV", "OMA"),
    "GAPB":     ("GAP aeropuertos pacifico Mexico BMV", "GAP"),
    "GCARSOA1": ("GCarso Slim Mexico BMV", "Carso"),
    "MEGACPO":  ("Megacable television Mexico BMV", "Megacable"),
    "LABB":     ("Genomma Lab Mexico BMV", "Genomma"),
    "CUERVO":   ("Jose Cuervo tequila Mexico BMV", "Cuervo"),
    "AC":       ("Arca Continental Coca-Cola Mexico BMV", "Arca Continental"),
    "VESTA":    ("Vesta parques industriales Mexico BMV", "Vesta"),
    "BOLSAA":   ("Bolsa Mexicana Valores BMV", "Bolsa Mexicana"),
    "GCC":      ("GCC cemento Mexico norte BMV", "GCC"),
    "HOTEL":    ("Hoteles City Mexico BMV", "City Express"),
    "POSADAS":  ("Posadas hoteles Mexico BMV", "Posadas"),
    "TLEVISA":  ("Televisa media Mexico BMV", "Televisa"),
    "HERDEZ":   ("Herdez alimentos Mexico BMV", "Herdez"),
    "GENTERA":  ("Gentera microfinanzas Mexico BMV", "Gentera"),
    "FUNO11":   ("FUNO fibra uno Mexico REIT BMV", "Fibra Uno"),
    "VISTA":    ("Vista Energy petroleo Argentina BMV", "Vista Energy"),
    "VOLARA":   ("Volaris aerolinea Mexico BMV", "Volaris"),
    "Q":        ("Quálitas seguros Mexico BMV", "Qualitas"),
    # USA SIC
    "AAPL":    ("Apple iPhone earnings stock", "Apple"),
    "MSFT":    ("Microsoft earnings cloud stock", "Microsoft"),
    "NVDA":    ("NVIDIA GPU AI stock", "NVIDIA"),
    "GOOGL":   ("Alphabet Google earnings stock", "Alphabet"),
    "META":    ("Meta Facebook Instagram stock", "Meta"),
    "AMZN":    ("Amazon AWS earnings stock", "Amazon"),
    "TSLA":    ("Tesla electric car earnings stock", "Tesla"),
    "AMD":     ("AMD semiconductor stock", "AMD"),
    "INTC":    ("Intel semiconductor stock", "Intel"),
    "JPM":     ("JPMorgan Chase bank earnings", "JPMorgan"),
    "BAC":     ("Bank of America earnings stock", "Bank of America"),
    "GS":      ("Goldman Sachs bank earnings", "Goldman"),
    "V":       ("Visa payment earnings stock", "Visa"),
    "MA":      ("Mastercard payment earnings stock", "Mastercard"),
    "KO":      ("Coca-Cola earnings dividend stock", "Coca-Cola"),
    "PEP":     ("PepsiCo earnings dividend stock", "PepsiCo"),
    "MCD":     ("McDonald's earnings stock", "McDonald"),
    "JNJ":     ("Johnson Johnson pharma earnings", "Johnson"),
    "PFE":     ("Pfizer pharma earnings stock", "Pfizer"),
    "XOM":     ("ExxonMobil oil earnings stock", "ExxonMobil"),
    "CVX":     ("Chevron oil earnings stock", "Chevron"),
    "AMX":     ("America Movil telecomunicaciones Mexico", "America Movil"),
    "FMX":     ("FEMSA ADR NYSE Mexico", "FEMSA"),
    # ETFs
    "SPY":     ("SP500 ETF market stock", "S&P 500"),
    "QQQ":     ("NASDAQ QQQ ETF tech", "NASDAQ"),
    "GLD":     ("gold price ETF GLD", "gold"),
    "SLV":     ("silver price ETF SLV", "silver"),
    "TLT":     ("treasury bonds TLT ETF", "treasury"),
    "EEM":     ("emerging markets ETF EEM", "emerging markets"),
    "EWZ":     ("Brazil ETF EWZ stock", "Brazil"),
    "FXI":     ("China ETF FXI stock", "China"),
    "XLE":     ("energy sector ETF XLE oil", "energy ETF"),
    "XLF":     ("financial sector ETF XLF bank", "financial ETF"),
    "XLK":     ("technology sector ETF XLK", "tech ETF"),
    # Cripto
    "IBIT":    ("Bitcoin ETF BlackRock IBIT", "Bitcoin"),
    "FBTC":    ("Bitcoin ETF Fidelity FBTC", "Bitcoin"),
    "ETHA":    ("Ethereum ETF iShares ETHA", "Ethereum"),
    "GBTC":    ("Grayscale Bitcoin Trust GBTC", "Bitcoin"),
    "MSTR":    ("MicroStrategy Bitcoin MSTR stock", "MicroStrategy"),
    "COIN":    ("Coinbase crypto exchange earnings", "Coinbase"),
    "MARA":    ("Marathon Digital Bitcoin mining", "Marathon"),
    "RIOT":    ("Riot Platforms Bitcoin mining", "Riot"),
    "CLSK":    ("CleanSpark Bitcoin mining", "CleanSpark"),
    # FIBRAs
    "FIBRAPL": ("Fibra Prologis REIT Mexico industrial", "Prologis"),
    "FINN13":  ("Fibra Inn hotel REIT Mexico", "Fibra Inn"),
}


def _scrape_articles(
    ticker: str,
    yf_symbol: str,
    days_back: int = 7,
    use_gdelt: bool = False,
) -> list[Article]:
    """Descarga artículos de todas las fuentes para un ticker. Sin scoring."""
    query_info = _SEARCH_QUERIES.get(ticker, (f"{ticker} stock", ticker))
    google_q   = query_info[0]
    keyword_mx = query_info[1] if len(query_info) > 1 else ticker

    articles: list[Article] = []
    is_mx = yf_symbol.endswith(".MX") or ticker in ("AMX", "FMX")
    lang  = "es-MX" if is_mx else "en-US"

    articles.extend(fetch_yfinance(yf_symbol, ticker))
    articles.extend(fetch_google_news_rss(google_q, ticker, lang=lang))

    if is_mx:
        articles.extend(fetch_elfinanciero_rss(ticker, keyword_mx))
        articles.extend(fetch_expansion_rss(ticker, keyword_mx))

    crypto_tickers = {"IBIT","FBTC","ETHA","GBTC","MSTR","COIN","MARA","RIOT","CLSK"}
    if ticker in crypto_tickers:
        currency = "ETH" if ticker == "ETHA" else "BTC"
        articles.extend(fetch_cryptopanic(ticker, currency))

    if use_gdelt:
        articles.extend(fetch_gdelt(google_q, ticker, days_back=days_back * 2))

    # Deduplicar por URL/título
    seen: set[str] = set()
    unique: list[Article] = []
    for a in articles:
        key = a.url or a.title
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    return unique


def get_news_features(
    ticker: str,
    yf_symbol: str,
    company_name: Optional[str] = None,
    days_back: int = 7,
    use_gdelt: bool = False,
    verbose: bool = False,
) -> dict[str, float]:
    """
    Pipeline completo: descarga noticias de todas las fuentes disponibles,
    corre sentiment (Gemini o keywords) y calcula las 4 features.

    Parameters
    ----------
    ticker      : nombre corto del ticker (e.g. "ALSEA")
    yf_symbol   : símbolo yfinance (e.g. "ALSEA.MX")
    company_name: nombre para búsqueda (si None, usa lookup interno)
    days_back   : ventana de noticias en días
    use_gdelt   : incluir GDELT (más lento, útil para backfill histórico)

    Returns
    -------
    dict con: news_sent_score, news_count_7d, news_sent_delta,
              news_sent_vol, n_articles, sources
    """
    cname = company_name or _SEARCH_QUERIES.get(ticker, (ticker, ticker))[1]

    # Scrape
    articles = _scrape_articles(ticker, yf_symbol, days_back=days_back, use_gdelt=use_gdelt)
    if verbose:
        print(f"  {ticker}: {len(articles)} artículos únicos")

    # Keyword scoring (siempre) + Gemini individual si GEMINI_NEWS_ENABLED=true
    scored = score_with_gemini(articles, cname)

    return _compute_features_from_articles(scored, days_back=days_back)


def batch_news_features(
    tickers: dict[str, str],
    days_back: int = 7,
    use_gdelt: bool = False,
    verbose: bool = True,
    save_cache: bool = True,
) -> pd.DataFrame:
    """
    Calcula news features para todos los tickers de un universo.

    Parameters
    ----------
    tickers   : dict nombre→símbolo yfinance (e.g. {"ALSEA": "ALSEA.MX"})
    days_back : ventana de noticias
    use_gdelt : incluir GDELT (lento, para backfill)
    save_cache: guardar resultado en data/news/YYYY-MM-DD.json

    Returns
    -------
    DataFrame con columnas: ticker, news_sent_score, news_count_7d,
                            news_sent_delta, news_sent_vol, n_articles
    """
    # ── Fase 1: scraping de todas las fuentes ────────────────────────────────
    tickers_articles: dict[str, list[Article]] = {}
    for name, symbol in tickers.items():
        if verbose:
            print(f"  [{name}] {symbol}...", end=" ", flush=True)
        try:
            articles = _scrape_articles(name, symbol, days_back=days_back, use_gdelt=use_gdelt)
            tickers_articles[name] = articles
            if verbose:
                print(f"{len(articles)} arts")
        except Exception as e:
            tickers_articles[name] = []
            if verbose:
                print(f"ERROR: {e}")

    # ── Fase 2: keyword scoring (siempre) + Gemini batch (si hay API key) ──
    # Keyword scoring individual
    for name, arts in tickers_articles.items():
        for a in arts:
            a.sentiment = _score_keywords(a.text())

    # Gemini: una sola llamada para todos los tickers con noticias
    gemini_scores = batch_score_gemini(tickers_articles, top_n_headlines=3)
    if gemini_scores and verbose:
        print(f"\n  Gemini batch: {len(gemini_scores)} tickers con score NLP\n")

    # ── Fase 3: computar features ─────────────────────────────────────────
    results = []
    for name, arts in tickers_articles.items():
        try:
            # Si tenemos score Gemini, aplicarlo como override del promedio
            feat = _compute_features_from_articles(arts, days_back=days_back)
            if name in gemini_scores:
                feat["news_sent_score"] = round(gemini_scores[name], 4)
            feat["ticker"] = name
            results.append(feat)
            if verbose:
                n    = feat["n_articles"]
                s    = feat["news_sent_score"]
                srcs = ",".join(feat.get("sources", []))
                g    = " (Gemini)" if name in gemini_scores else ""
                print(f"  {name:<15} {n:>3} arts  sent={s:+.2f}{g}  [{srcs}]")
        except Exception as e:
            logger.warning(f"{name}: error en news features — {e}")
            results.append({
                "ticker":          name,
                "news_sent_score": 0.0,
                "news_count_7d":   0.0,
                "news_sent_delta": 0.0,
                "news_sent_vol":   0.0,
                "n_articles":      0,
                "sources":         [],
            })

    df = pd.DataFrame(results).set_index("ticker")

    if save_cache:
        today = datetime.now().strftime("%Y-%m-%d")
        cache_path = NEWS_DIR / f"{today}.json"
        cache_data = df.reset_index().to_dict(orient="records")
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
        (NEWS_DIR / "latest.json").write_text(
            json.dumps(cache_data, ensure_ascii=False, indent=2)
        )
        if verbose:
            print(f"\n  Guardado en: {cache_path}")

    return df


def load_cached_news_features(date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Carga features de noticias del cache en disco.
    Si date=None, carga 'latest.json'.
    """
    if date:
        path = NEWS_DIR / f"{date}.json"
    else:
        path = NEWS_DIR / "latest.json"

    if not path.exists():
        return None

    data = json.loads(path.read_text())
    df   = pd.DataFrame(data)
    if "ticker" in df.columns:
        df = df.set_index("ticker")
    return df


# Columnas de features de noticias (para añadir a FEATURE_COLS si se desea)
NEWS_FEATURE_COLS = [
    "news_sent_score",
    "news_count_7d",
    "news_sent_delta",
    "news_sent_vol",
]
