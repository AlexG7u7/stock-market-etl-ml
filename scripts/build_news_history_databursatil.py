#!/usr/bin/env python3
"""
Backfill panel de noticias desde snapshots DataBursátil acumulados.

No usa GDELT. Requiere snapshots diarios (scripts/databursatil_news_snapshot.py).

Uso:
  python scripts/build_news_history_databursatil.py --universe bmv
  python scripts/build_news_history_databursatil.py --snapshot-today --universe bmv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from scripts.backtest_topk import load_universe_tickers
from src.ml.databursatil_news import (
    build_daily_panel_from_snapshots,
    list_snapshot_dates,
    merge_into_daily_features_parquet,
    save_daily_snapshot,
)
from src.ml.news_history import history_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Panel histórico DataBursátil")
    parser.add_argument("--universe", default="bmv")
    parser.add_argument("--snapshot-today", action="store_true",
                        help="Tomar snapshot de hoy antes de reconstruir")
    args = parser.parse_args()

    tickers = list(load_universe_tickers(args.universe).keys())
    dates = list_snapshot_dates()

    print(f"\n══ DataBursátil history — {len(tickers)} tickers ══")
    print(f"   Snapshots en disco: {len(dates)}")
    if dates:
        print(f"   Rango: {dates[0]} → {dates[-1]}")

    if args.snapshot_today:
        save_daily_snapshot()

    if not list_snapshot_dates():
        print("\n❌ Sin snapshots. Corre primero:")
        print("   python scripts/databursatil_news_snapshot.py\n")
        sys.exit(1)

    panel = build_daily_panel_from_snapshots(tickers, verbose=True)
    merge_into_daily_features_parquet(panel)
    stats = history_stats()
    print(f"\n✅ Stats: {json.dumps(stats, indent=2)}\n")


if __name__ == "__main__":
    main()
