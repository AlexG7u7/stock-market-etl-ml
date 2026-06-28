"""
Construye / actualiza la base de datos local completa (todos los universos).

Universos:
  bmv    — 31 acciones mexicanas (IPC + extensión)
  usa    — 23 acciones USA disponibles en GBM SIC
  etf    — 22 ETFs (mercado, sectores, commodities, renta fija)
  crypto — 9 proxies de criptomonedas (ETFs BTC/ETH + mineras)
  fibra  — 3 FIBRAs mexicanas (REITs)
  macro  — 4 activos macro (USD/MXN, NAFTRAC, WTI, SP500)

Uso:
    python scripts/build_database.py              # descarga / actualiza todo
    python scripts/build_database.py --group bmv  # solo un universo
    python scripts/build_database.py --update     # solo días nuevos (incremental)

Tiempo estimado primera vez: ~8-12 minutos (todos los universos).
Actualizaciones diarias: ~30 segundos.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store import (
    update_all, update_group, info,
    BMV_TICKERS, USA_TICKERS, ETF_TICKERS,
    CRYPTO_TICKERS, FIBRA_TICKERS, MACRO_TICKERS,
    UNIVERSE_GROUPS,
)

GROUP_LABELS = {
    "bmv":    ("Acciones BMV",     BMV_TICKERS),
    "usa":    ("Acciones USA SIC", USA_TICKERS),
    "etf":    ("ETFs",             ETF_TICKERS),
    "crypto": ("Cripto (proxies)", CRYPTO_TICKERS),
    "fibra":  ("FIBRAs mexicanas", FIBRA_TICKERS),
    "macro":  ("Macro",            MACRO_TICKERS),
}


def main():
    parser = argparse.ArgumentParser(description="Construir / actualizar BD de mercado")
    parser.add_argument("--update", action="store_true",
                        help="Solo descarga días nuevos (incremental)")
    parser.add_argument("--group", choices=list(UNIVERSE_GROUPS.keys()), default=None,
                        help="Actualizar solo un universo (bmv|usa|etf|crypto|fibra|macro)")
    args = parser.parse_args()

    total = sum(len(t) for t in UNIVERSE_GROUPS.values())

    print(f"\n{'═'*62}")
    print(f"  BASE DE DATOS MULTI-UNIVERSO  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.group:
        label, tickers = GROUP_LABELS[args.group]
        print(f"  Grupo: {label} ({len(tickers)} símbolos)")
    else:
        print(f"  {total} símbolos en {len(UNIVERSE_GROUPS)} universos:")
        for key, (label, tickers) in GROUP_LABELS.items():
            print(f"    {key:<8} {label:<22} {len(tickers):>3} tickers")
    print(f"{'═'*62}\n")

    if args.group:
        label, _ = GROUP_LABELS[args.group]
        print(f"── {label} {'─'*40}\n")
        update_group(args.group, verbose=True)
    else:
        for key, (label, _) in GROUP_LABELS.items():
            print(f"── {label} {'─'*40}\n")
            update_group(key, verbose=True)
            print()

    print()
    info()


if __name__ == "__main__":
    main()
