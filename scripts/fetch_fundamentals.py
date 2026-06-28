"""
Descarga y cachea fundamentales (estados financieros) de todas las emisoras BMV.

Salida: data/fundamentals.parquet con columnas
  [ticker, quarter_end, fund_gross_margin, fund_oper_margin, fund_net_margin,
   fund_revenue_yoy, fund_earnings_yoy, available_date]

Uso:
  python -m scripts.fetch_fundamentals
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.fundamentals import fetch_ticker, EMISORA_MAP  # noqa: E402
from src.data.store import BMV_TICKERS                       # noqa: E402

OUT = Path(__file__).parent.parent / "data" / "fundamentals.parquet"


def main():
    load_dotenv()
    token = os.environ.get("DATABURSATIL_API_TOKEN")
    if not token:
        print("ERROR: falta DATABURSATIL_API_TOKEN en .env")
        sys.exit(1)

    frames = []
    ok, fail = [], []
    for ticker in BMV_TICKERS:
        if ticker not in EMISORA_MAP:
            fail.append(f"{ticker} (sin mapeo)")
            continue
        df = fetch_ticker(ticker, token)
        if df.empty:
            fail.append(ticker)
            print(f"  ✗ {ticker:10s} sin datos")
            continue
        df = df.reset_index().rename(columns={"index": "quarter_end"})
        df.insert(0, "ticker", ticker)
        frames.append(df)
        ok.append(ticker)
        print(f"  ✓ {ticker:10s} {len(df):2d} trimestres "
              f"({df['quarter_end'].min().date()} → {df['quarter_end'].max().date()})")
        time.sleep(0.2)

    if not frames:
        print("\nNo se obtuvo ningún dato.")
        sys.exit(1)

    out = pd.concat(frames, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)

    print(f"\n{'='*60}")
    print(f"Guardado: {OUT}")
    print(f"  Tickers OK:   {len(ok)}/{len(BMV_TICKERS)}")
    print(f"  Filas totales: {len(out)}")
    if fail:
        print(f"  Fallaron:     {', '.join(fail)}")


if __name__ == "__main__":
    main()
