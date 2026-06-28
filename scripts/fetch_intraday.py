"""
Descarga y cachea barras intradía (5m) de tickers líquidos BMV vía DataBursátil.

El histórico intradía solo existe desde ~nov-2024. Guardamos por ticker en
data/intraday/{ticker}.parquet con columnas [datetime, price].

Uso:
    python -m scripts.fetch_intraday
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

BASE = "https://api.databursatil.com"
OUT_DIR = ROOT / "data" / "intraday"
INTERVAL = "5m"
START = "2024-11-01"

# Ticker interno → emisora_serie (formato intradía, con sufijo de serie)
INTRADAY_MAP: dict[str, str] = {
    "WALMEX": "WALMEX*",   "FEMSAUBD": "FEMSAUBD", "GMEXICOB": "GMEXICOB",
    "CEMEXCPO": "CEMEXCPO","GFNORTEO": "GFNORTEO", "BIMBOA": "BIMBOA",
    "ALSEA": "ALSEA*",     "KIMBERA": "KIMBERA",   "GRUMAB": "GRUMAB",
    "ASURB": "ASURB",      "GAPB": "GAPB",         "ORBIA": "ORBIA*",
    "AC": "AC*",           "VESTA": "VESTA*",      "PINFRA": "PINFRA*",
    "OMAB": "OMAB",        "MEGACPO": "MEGACPO",   "TLEVISA": "TLEVISACPO",
}


def month_ranges(start: str, end: pd.Timestamp):
    """Genera (inicio, final) por mes desde start hasta end."""
    cur = pd.Timestamp(start).replace(day=1)
    end = pd.Timestamp(end)
    while cur <= end:
        last = (cur + pd.offsets.MonthEnd(0))
        yield cur.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
        cur = cur + pd.offsets.MonthBegin(1)


def fetch_batch(emisoras: list[str], token: str, inicio: str, final: str) -> dict:
    """GET intradia para un batch (≤10 emisoras). Devuelve {emisora_serie: {dt: price}}."""
    p = {"token": token, "emisora_serie": ",".join(emisoras),
         "bolsa": "BMV", "intervalo": INTERVAL, "inicio": inicio, "final": final}
    try:
        r = requests.get(f"{BASE}/v2/intradia", params=p, timeout=60)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {k: v for k, v in d.items() if isinstance(v, dict)}
    except Exception as e:
        print(f"    ! {inicio}: {e}")
        return {}


def main():
    load_dotenv()
    token = os.environ.get("DATABURSATIL_API_TOKEN")
    if not token:
        print("ERROR: falta DATABURSATIL_API_TOKEN en .env"); sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().normalize()

    # ── inverso: emisora_serie → ticker interno ──
    inv = {v: k for k, v in INTRADAY_MAP.items()}
    emisoras = list(INTRADAY_MAP.values())
    batches = [emisoras[i:i + 10] for i in range(0, len(emisoras), 10)]

    rows: dict[str, list] = {t: [] for t in INTRADAY_MAP}
    months = list(month_ranges(START, today))
    print(f"Descargando {INTERVAL} | {len(INTRADAY_MAP)} tickers × {len(months)} meses "
          f"({len(batches)} batches/mes)\n")

    for inicio, final in months:
        got = 0
        for batch in batches:
            data = fetch_batch(batch, token, inicio, final)
            for em_serie, series in data.items():
                t = inv.get(em_serie)
                if not t:
                    continue
                for dt, price in series.items():
                    rows[t].append((dt, price))
                    got += 1
            time.sleep(0.15)
        print(f"  {inicio[:7]}: {got:>6} barras")

    # ── guardar por ticker ──
    print()
    total = 0
    for t, recs in rows.items():
        if not recs:
            print(f"  ✗ {t:10s} sin datos"); continue
        df = pd.DataFrame(recs, columns=["datetime", "price"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
        df.to_parquet(OUT_DIR / f"{t}.parquet", index=False)
        total += len(df)
        print(f"  ✓ {t:10s} {len(df):>6} barras "
              f"({df['datetime'].min().date()} → {df['datetime'].max().date()})")
    print(f"\nTotal: {total:,} barras intradía en {OUT_DIR}")


if __name__ == "__main__":
    main()
