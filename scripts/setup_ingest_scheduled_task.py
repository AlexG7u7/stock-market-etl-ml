"""
Configura Windows Scheduled Task para pipeline completo de ingestas.

Reemplaza el task legacy de solo WALMEX/ALSEA.

Uso (PowerShell como Admin en el servidor):
    python scripts/setup_ingest_scheduled_task.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TASK_NAME = "StockMarket-DataIngest"
PROJECT_PATH = Path(r"C:\Projects\stock-market")
PYTHON = PROJECT_PATH / "venv" / "Scripts" / "python.exe"
INGEST_SCRIPT = PROJECT_PATH / "scripts" / "run_all_ingests.py"


def _batch_content() -> str:
    py = str(PYTHON)
    script = str(INGEST_SCRIPT)
    root = str(PROJECT_PATH)
    return f"""@echo off
cd /d {root}
echo ========================================
echo DATA INGEST - %DATE% %TIME%
echo ========================================
"{py}" "{script}" --all
if errorlevel 1 (
    echo ERROR: ingest pipeline fallo
    exit /b 1
)
echo OK: ingest completado
"""


def main() -> int:
    batch_path = PROJECT_PATH / "scripts" / "run_ingest_daily.bat"
    batch_path.write_text(_batch_content(), encoding="utf-8")
    print(f"Batch: {batch_path}")

    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True)

    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", str(batch_path),
        "/SC", "WEEKLY",
        "/D", "MON,TUE,WED,THU,FRI",
        "/ST", "07:00",
        "/F",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        return 1

    print(f"Task creada: {TASK_NAME} — Lun–Vie 07:00")
    print("Incluye: OHLCV + news + intraday + fundamentals + SQL + audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
