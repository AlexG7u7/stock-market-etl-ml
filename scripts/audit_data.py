"""
Auditoría de cobertura y calidad de datos — DATA-001.

Reporta OHLCV, intradía, noticias y freshness por fuente.

Uso:
    python scripts/audit_data.py
    python scripts/audit_data.py --json data/eval/data_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.data.store import MARKET_DIR, BMV_TICKERS
from src.data.universes import UNIVERSES
from src.ml.intraday_features import INTRADAY_DIR

NEWS_DIR = ROOT / "data" / "news"
BMV_KEY = "🇲🇽 Acciones BMV"
MIN_OHLCV_ROWS = 500
MIN_INTRADAY_BARS = 1000


def _audit_market() -> dict:
    files = list(MARKET_DIR.glob("*.parquet")) if MARKET_DIR.exists() else []
    bmv_expected = set(BMV_TICKERS.keys())
    bmv_found: dict[str, dict] = {}
    stale: list[str] = []

    for ticker in bmv_expected:
        sym = BMV_TICKERS[ticker]
        safe = sym.replace("^", "").replace("=", "_")
        path = MARKET_DIR / f"{safe}.parquet"
        if not path.exists():
            path = MARKET_DIR / f"{sym}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        idx = pd.to_datetime(df.index)
        last = idx.max()
        rows = len(df)
        bmv_found[ticker] = {
            "rows": rows,
            "last_date": str(last.date()) if pd.notna(last) else None,
            "ok": rows >= MIN_OHLCV_ROWS,
        }
        if rows < MIN_OHLCV_ROWS:
            stale.append(ticker)

    return {
        "total_parquets": len(files),
        "bmv_expected": len(bmv_expected),
        "bmv_with_data": len(bmv_found),
        "bmv_missing": sorted(bmv_expected - set(bmv_found)),
        "bmv_low_history": stale,
        "sample": dict(list(bmv_found.items())[:5]),
    }


def _audit_intraday() -> dict:
    if not INTRADAY_DIR.exists():
        return {"tickers": 0, "missing_bmv": list(BMV_TICKERS.keys())}

    mapped = set(BMV_TICKERS.keys()) & {p.stem for p in INTRADAY_DIR.glob("*.parquet")}
    details: dict[str, dict] = {}
    weak: list[str] = []

    for p in sorted(INTRADAY_DIR.glob("*.parquet")):
        df = pd.read_parquet(p)
        n = len(df)
        last = None
        if n and "datetime" in df.columns:
            last = str(pd.to_datetime(df["datetime"]).max())
        details[p.stem] = {"bars": n, "last_bar": last, "ok": n >= MIN_INTRADAY_BARS}
        if n < MIN_INTRADAY_BARS:
            weak.append(p.stem)

    return {
        "tickers": len(details),
        "bmv_covered": len(mapped),
        "bmv_missing_intraday": sorted(set(BMV_TICKERS) - mapped),
        "low_bar_count": weak,
        "sample": dict(list(details.items())[:5]),
    }


def _audit_news() -> dict:
    path = NEWS_DIR / "latest.json"
    if not path.exists():
        return {"status": "missing", "path": str(path)}

    data = json.loads(path.read_text())
    total = len(data)
    no_articles = [r["ticker"] for r in data if r.get("n_articles", 0) == 0]
    fake_sent = [
        r["ticker"] for r in data
        if r.get("n_articles", 0) == 0 and abs(r.get("news_sent_score", 0)) > 1e-6
    ]
    with_articles = total - len(no_articles)
    sources: dict[str, int] = {}
    for r in data:
        for s in r.get("sources") or []:
            sources[s] = sources.get(s, 0) + 1

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()

    return {
        "cache_path": str(path),
        "cache_updated_utc": mtime,
        "tickers": total,
        "with_articles": with_articles,
        "without_articles": len(no_articles),
        "pct_coverage": round(100 * with_articles / max(total, 1), 1),
        "neutral_violations": fake_sent,
        "no_articles_tickers": no_articles[:15],
        "source_counts": sources,
        "sent_mean": round(
            sum(r.get("news_sent_score", 0) for r in data if r.get("n_articles", 0) > 0)
            / max(with_articles, 1),
            3,
        ),
    }


def run_audit() -> dict:
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "market": _audit_market(),
        "intraday": _audit_intraday(),
        "news": _audit_news(),
    }


def _print_report(report: dict) -> None:
    m = report["market"]
    i = report["intraday"]
    n = report["news"]

    print("\n" + "=" * 60)
    print("  DATA AUDIT — stock-market")
    print("=" * 60)

    print(f"\n📈 OHLCV (data/market/)")
    print(f"   Parquets totales:     {m['total_parquets']}")
    print(f"   BMV con datos:        {m['bmv_with_data']}/{m['bmv_expected']}")
    if m["bmv_missing"]:
        print(f"   BMV sin parquet:      {', '.join(m['bmv_missing'][:10])}")

    print(f"\n⏱  Intradía 5m (data/intraday/)")
    print(f"   Tickers con barras:   {i['tickers']}")
    print(f"   BMV cubiertos:        {i.get('bmv_covered', 0)}/{m['bmv_expected']}")
    if i.get("bmv_missing_intraday"):
        print(f"   BMV sin intradía:     {', '.join(i['bmv_missing_intraday'][:10])}")

    print(f"\n📰 Noticias (data/news/latest.json)")
    if n.get("status") == "missing":
        print("   ⚠️  Cache no encontrado — correr refresh_market_data.py --news")
    else:
        print(f"   Cache actualizado:    {n.get('cache_updated_utc', '?')}")
        print(f"   Con artículos:        {n['with_articles']}/{n['tickers']} ({n['pct_coverage']}%)")
        print(f"   Sent medio (con news): {n.get('sent_mean', 0):+.3f}")
        if n.get("neutral_violations"):
            print(f"   ⚠️  Sent sin artículos: {n['neutral_violations']}")
        if n.get("source_counts"):
            print(f"   Fuentes:              {n['source_counts']}")

    print("\n" + "=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría de datos del proyecto")
    parser.add_argument("--json", type=str, help="Exportar reporte JSON")
    args = parser.parse_args()

    report = run_audit()
    _print_report(report)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"JSON guardado: {out}")


if __name__ == "__main__":
    main()
