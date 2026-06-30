"""
Punto de entrada único para refrescar datos auxiliares del modelo (noticias + intradía).

Uso:
    python scripts/refresh_market_data.py --all
    python scripts/refresh_market_data.py --news
    python scripts/refresh_market_data.py --intraday
    python scripts/refresh_market_data.py --news --days 14

Cron (ejemplo, antes del mercado MX):
    0 7 * * 1-5 cd /path/stock-market && python scripts/refresh_market_data.py --all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.data.universes import UNIVERSES  # noqa: E402
from src.ml.news import NEWS_DIR, batch_news_features  # noqa: E402

BMV_UNIVERSE = "🇲🇽 Acciones BMV"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _publish_latest(records: list[dict], dated_path: Path) -> Path:
    """Escribe dated JSON y copia a data/news/latest.json."""
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    dated_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    latest_path = NEWS_DIR / "latest.json"
    latest_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return latest_path


def refresh_news(days_back: int = 7) -> None:
    """Descarga y procesa noticias para todo el universo BMV."""
    cfg = UNIVERSES.get(BMV_UNIVERSE)
    if cfg is None:
        raise RuntimeError(f"Universo no encontrado: {BMV_UNIVERSE}")

    tickers = cfg["tickers"]
    logger.info("Noticias BMV — %d tickers, ventana %d días", len(tickers), days_back)

    df = batch_news_features(
        tickers=tickers,
        days_back=days_back,
        verbose=True,
        save_cache=False,
    )
    records = df.reset_index().to_dict(orient="records")
    today = datetime.now().strftime("%Y-%m-%d")
    dated_path = NEWS_DIR / f"{today}.json"
    latest_path = _publish_latest(records, dated_path)

    sent_mean = df["news_sent_score"].mean() if "news_sent_score" in df.columns else 0.0
    logger.info(
        "Noticias listas — %d tickers, sent medio %+.3f",
        len(df),
        sent_mean,
    )
    logger.info("Guardado: %s", dated_path)
    logger.info("Alias:    %s", latest_path)


def refresh_intraday(full: bool = False) -> None:
    """Descarga barras intradía 5m vía DataBursátil (scripts/fetch_intraday)."""
    logger.info("Intradía — iniciando fetch DataBursátil (full=%s)", full)
    from scripts.fetch_intraday import main as fetch_intraday_main

    fetch_intraday_main(full=full)
    logger.info("Intradía — completado")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refrescar datos de mercado (news + intradía)")
    parser.add_argument("--news", action="store_true", help="Refrescar noticias BMV")
    parser.add_argument("--intraday", action="store_true", help="Refrescar barras intradía 5m")
    parser.add_argument("--all", action="store_true", help="Ejecutar news + intraday")
    parser.add_argument("--days", type=int, default=7, help="Ventana de noticias (días)")
    args = parser.parse_args()

    if not (args.news or args.intraday or args.all):
        parser.error("Indica --news, --intraday o --all")

    logger.info("═" * 50)
    logger.info("REFRESH MARKET DATA — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("═" * 50)

    if args.all or args.news:
        refresh_news(days_back=args.days)

    if args.all or args.intraday:
        refresh_intraday()

    logger.info("Refresh completado")


if __name__ == "__main__":
    main()
