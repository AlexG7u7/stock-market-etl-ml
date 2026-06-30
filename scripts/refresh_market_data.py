"""
Punto de entrada legacy — delega en run_all_ingests.py.

Preferir:
    python scripts/run_all_ingests.py --all
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def refresh_news(
    days_back: int = 7,
    universe: str | None = None,
    gdelt: bool = False,
) -> None:
    """Descarga noticias — todos los universos por default."""
    from scripts.fetch_news import run_fetch_news

    result = run_fetch_news(
        days_back=days_back,
        universe=universe,
        gdelt=gdelt,
        save_cache=True,
        verbose=True,
    )
    logger.info(
        "Noticias listas — %d tickers (%s)",
        result["total_tickers"],
        result["universe"],
    )
    if result.get("paths", {}).get("latest"):
        logger.info("Alias: %s", result["paths"]["latest"])


def refresh_intraday(full: bool = False) -> None:
    """Descarga barras intradía 5m vía DataBursátil."""
    logger.info("Intradía — iniciando fetch DataBursátil (full=%s)", full)
    from scripts.fetch_intraday import main as fetch_intraday_main

    fetch_intraday_main(full=full)
    logger.info("Intradía — completado")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refrescar news + intradía (wrapper legacy)")
    parser.add_argument("--news", action="store_true")
    parser.add_argument("--intraday", action="store_true")
    parser.add_argument("--all", action="store_true", help="news + intraday")
    parser.add_argument("--days", type=int, default=7, help="Ventana noticias")
    parser.add_argument("--universe", choices=["bmv", "usa", "etf", "crypto", "fibra"],
                        help="Solo un universo de noticias")
    args = parser.parse_args()

    if not (args.news or args.intraday or args.all):
        parser.error("Indica --news, --intraday o --all")

    from scripts.run_all_ingests import run_ingests

    report = run_ingests(
        ohlcv=False,
        news=args.all or args.news,
        intraday=args.all or args.intraday,
        fundamentals=False,
        sql=False,
        audit=False,
        news_days=args.days,
        news_universe=args.universe,
        intraday_full=False,
    )
    sys.exit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
