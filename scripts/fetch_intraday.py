"""
Descarga y cachea barras intradía (5m) de tickers líquidos BMV vía DataBursátil.

El histórico intradía solo existe desde ~nov-2024. Guardamos por ticker en
data/intraday/{ticker}.parquet con columnas [datetime, price] y opcionalmente
[volume] si la API devuelve volumen por barra.

Modo incremental (default): omite meses ya presentes en el parquet existente.
Usar --full para re-descargar todo desde START.

Uso:
    python -m scripts.fetch_intraday
    python -m scripts.fetch_intraday --full
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

BASE = "https://api.databursatil.com"
OUT_DIR = ROOT / "data" / "intraday"
INTERVAL = "5m"
START = "2024-11-01"

from src.data.bmv_catalog import INTRADAY_MAP  # noqa: E402


def month_ranges(start: str, end: pd.Timestamp):
    """Genera (inicio, final) por mes desde start hasta end."""
    cur = pd.Timestamp(start).replace(day=1)
    end = pd.Timestamp(end)
    while cur <= end:
        last = (cur + pd.offsets.MonthEnd(0))
        yield cur.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
        cur = cur + pd.offsets.MonthBegin(1)


def parse_bar(entry) -> tuple[float, float | None]:
    """Extrae (price, volume) de una barra API — escalar o dict con u/v."""
    if isinstance(entry, (int, float)):
        return float(entry), None
    if isinstance(entry, dict):
        price = entry.get("u") or entry.get("precio") or entry.get("p")
        if price is None:
            for key, val in entry.items():
                if key in ("v", "volumen", "volume", "o", "i"):
                    continue
                if isinstance(val, (int, float)):
                    price = val
                    break
        vol = entry.get("v") or entry.get("volumen") or entry.get("volume")
        if price is None:
            raise ValueError(f"bar sin precio: {entry!r}")
        return float(price), (float(vol) if vol is not None else None)
    raise TypeError(f"tipo de barra no soportado: {type(entry).__name__}")


def fetch_batch(emisoras: list[str], token: str, inicio: str, final: str) -> dict:
    """GET intradia para un batch (≤10 emisoras). Devuelve {emisora_serie: {dt: bar}}."""
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


def months_in_parquet(path: Path) -> set[str]:
    """Meses YYYY-MM ya cubiertos en un parquet existente."""
    if not path.exists():
        return set()
    df = pd.read_parquet(path, columns=["datetime"])
    if df.empty:
        return set()
    return set(pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m"))


def save_ticker_parquet(ticker: str, recs: list[tuple]) -> int:
    """Merge recs con parquet existente y guarda. recs: (dt, price) o (dt, price, vol)."""
    path = OUT_DIR / f"{ticker}.parquet"
    has_vol = any(len(r) > 2 and r[2] is not None for r in recs)

    if has_vol:
        new_df = pd.DataFrame(recs, columns=["datetime", "price", "volume"])
    else:
        new_df = pd.DataFrame([(r[0], r[1]) for r in recs], columns=["datetime", "price"])

    new_df["datetime"] = pd.to_datetime(new_df["datetime"])

    if path.exists():
        old = pd.read_parquet(path)
        old["datetime"] = pd.to_datetime(old["datetime"])
        cols = ["datetime", "price"]
        if "volume" in old.columns or "volume" in new_df.columns:
            cols.append("volume")
            for frame in (old, new_df):
                if "volume" not in frame.columns:
                    frame["volume"] = np.nan
        new_df = pd.concat([old, new_df], ignore_index=True)

    new_df = new_df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    new_df.to_parquet(path, index=False)
    return len(new_df)


def main(full: bool = False) -> None:
    """Descarga barras intradía. ``full=True`` ignora cache incremental."""
    load_dotenv()
    token = os.environ.get("DATABURSATIL_API_TOKEN")
    if not token:
        print("ERROR: falta DATABURSATIL_API_TOKEN en .env")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().normalize()

    inv = {v: k for k, v in INTRADAY_MAP.items()}
    emisoras = list(INTRADAY_MAP.values())
    batches = [emisoras[i:i + 10] for i in range(0, len(emisoras), 10)]

    all_months = list(month_ranges(START, today))
    mode = "full" if full else "incremental"
    print(f"Descargando {INTERVAL} | {len(INTRADAY_MAP)} tickers | modo {mode}\n")

    rows: dict[str, list] = {t: [] for t in INTRADAY_MAP}
    skipped_months = 0

    for inicio, final in all_months:
        month_key = inicio[:7]
        if not full:
            # Skip month if ALL tickers already have it (conservative: skip if any has it)
            covered = sum(
                1 for t in INTRADAY_MAP
                if month_key in months_in_parquet(OUT_DIR / f"{t}.parquet")
            )
            if covered == len(INTRADAY_MAP):
                skipped_months += 1
                continue

        got = 0
        for batch in batches:
            data = fetch_batch(batch, token, inicio, final)
            for em_serie, series in data.items():
                t = inv.get(em_serie)
                if not t:
                    continue
                if not full and month_key in months_in_parquet(OUT_DIR / f"{t}.parquet"):
                    continue
                for dt, bar in series.items():
                    price, vol = parse_bar(bar)
                    if vol is not None:
                        rows[t].append((dt, price, vol))
                    else:
                        rows[t].append((dt, price))
                    got += 1
            time.sleep(0.15)
        if got:
            print(f"  {month_key}: {got:>6} barras nuevas")

    if skipped_months:
        print(f"\n  ({skipped_months} meses omitidos — ya en cache; usar --full para forzar)")

    print()
    total = 0
    for t, recs in rows.items():
        path = OUT_DIR / f"{t}.parquet"
        if not recs and path.exists():
            df = pd.read_parquet(path)
            total += len(df)
            print(f"  = {t:10s} {len(df):>6} barras (sin cambios)")
            continue
        if not recs:
            print(f"  ✗ {t:10s} sin datos")
            continue
        n = save_ticker_parquet(t, recs)
        df = pd.read_parquet(path)
        vol_note = " +vol" if "volume" in df.columns and df["volume"].notna().any() else ""
        total += n
        print(f"  ✓ {t:10s} {n:>6} barras{vol_note} "
              f"({df['datetime'].min().date()} → {df['datetime'].max().date()})")
    print(f"\nTotal: {total:,} barras intradía en {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga barras intradía 5m BMV")
    parser.add_argument(
        "--full", action="store_true",
        help="Re-descargar todos los meses (ignora cache incremental)",
    )
    args = parser.parse_args()
    main(full=args.full)
