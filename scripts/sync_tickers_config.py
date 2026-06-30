"""
Sincroniza tickers_activos en config/tickers_config.yml desde bmv_catalog.

Uso:
    python scripts/sync_tickers_config.py
    python scripts/sync_tickers_config.py --check   # exit 1 si desincronizado
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.bmv_catalog import sql_ticker_list  # noqa: E402

CONFIG_PATH = ROOT / "config" / "tickers_config.yml"


def _load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def sync(*, check_only: bool = False) -> int:
    expected = sql_ticker_list()
    config = _load_config()
    current = config.get("tickers_activos") or []

    if current == expected:
        print(f"OK — {len(expected)} tickers en sync")
        return 0

    if check_only:
        missing = sorted(set(expected) - set(current))
        extra = sorted(set(current) - set(expected))
        print(f"DESYNC — esperados {len(expected)}, actuales {len(current)}")
        if missing:
            print(f"  Faltan: {missing}")
        if extra:
            print(f"  Sobran: {extra}")
        return 1

    config["tickers_activos"] = expected
    header = (
        "# Configuración de Tickers Activos — ETL incremental SQL Server\n"
        "# Generado desde src/data/bmv_catalog.py (36 emisoras líquidas BMV)\n"
        "# Para regenerar lista: python scripts/sync_tickers_config.py\n\n"
    )
    body = yaml.dump(
        config,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    CONFIG_PATH.write_text(header + body, encoding="utf-8")
    print(f"Actualizado {CONFIG_PATH} — {len(expected)} tickers")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Solo verificar, no escribir")
    args = parser.parse_args()
    sys.exit(sync(check_only=args.check))


if __name__ == "__main__":
    main()
