"""
Construye la base de datos local completa.

  1. Descarga historial MÁXIMO disponible en Yahoo Finance para:
     - 19 tickers del IPC
     - USD/MXN, NAFTRAC, WTI, S&P 500
  2. Guarda todo en data/market/*.parquet (Snappy comprimido)
  3. Imprime resumen del store

Ejecución:
    python scripts/build_database.py          # descarga todo desde cero
    python scripts/build_database.py --update # solo agrega días nuevos

Tiempo estimado primera vez: ~3-5 minutos.
Actualizaciones diarias: ~15 segundos.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store import update_all, info, ALL_SYMBOLS


def main():
    parser = argparse.ArgumentParser(description="Construir / actualizar BD de mercado")
    parser.add_argument("--update", action="store_true",
                        help="Solo descarga días nuevos (más rápido)")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  BASE DE DATOS BMV  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {len(ALL_SYMBOLS)} símbolos: 19 tickers IPC + 4 macro")
    print(f"{'═'*60}\n")

    print("Descargando / actualizando...\n")
    update_all(verbose=True)

    print()
    info()


if __name__ == "__main__":
    main()
