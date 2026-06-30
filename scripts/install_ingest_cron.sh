#!/usr/bin/env bash
# Instala cron jobs para ingestas automáticas (Mac/Linux).
#
# Horarios (hora local del sistema — ajusta TZ si es necesario):
#   Lun–Vie 07:00  — pre-apertura: pipeline completo (SQL si hay credenciales)
#   Lun–Vie 18:30  — post-cierre: OHLCV + noticias (todos los universos)
#   Dom    08:00  — fundamentales forzados
#   Dom    09:00  — noticias con GDELT (backfill semanal)
#
# Uso:
#   chmod +x scripts/install_ingest_cron.sh
#   ./scripts/install_ingest_cron.sh
#   ./scripts/install_ingest_cron.sh --uninstall

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/venv/bin/python"
LOG_DIR="${ROOT}/logs/ingest"
MARKER="# stock-market-ingest"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: no existe ${PY} — crea el venv primero."
  exit 1
fi

mkdir -p "$LOG_DIR"

CRON_PRE="${MARKER} pre-market"
LINE_PRE="0 7 * * 1-5 cd ${ROOT} && ${PY} scripts/run_all_ingests.py --all >> ${LOG_DIR}/pre_market.log 2>&1 ${CRON_PRE}"

CRON_POST="${MARKER} post-close"
LINE_POST="30 18 * * 1-5 cd ${ROOT} && ${PY} scripts/run_all_ingests.py --ohlcv --news --skip-audit >> ${LOG_DIR}/post_close.log 2>&1 ${CRON_POST}"

CRON_FUND="${MARKER} fundamentals"
LINE_FUND="0 8 * * 0 cd ${ROOT} && ${PY} scripts/run_all_ingests.py --fundamentals --force-fundamentals --skip-audit >> ${LOG_DIR}/fundamentals.log 2>&1 ${CRON_FUND}"

CRON_GDELT="${MARKER} gdelt-weekly"
LINE_GDELT="0 9 * * 0 cd ${ROOT} && ${PY} scripts/run_all_ingests.py --news --news-gdelt --skip-audit >> ${LOG_DIR}/gdelt.log 2>&1 ${CRON_GDELT}"

uninstall() {
  crontab -l 2>/dev/null | grep -v "${MARKER}" | crontab - || true
  echo "Cron jobs ${MARKER} eliminados."
}

install() {
  uninstall
  (crontab -l 2>/dev/null; echo "$LINE_PRE"; echo "$LINE_POST"; echo "$LINE_FUND"; echo "$LINE_GDELT") | crontab -
  echo "Cron instalado:"
  echo "  • Lun–Vie 07:00  → run_all_ingests.py --all"
  echo "  • Lun–Vie 18:30  → --ohlcv --news"
  echo "  • Dom    08:00  → --fundamentals --force-fundamentals"
  echo "  • Dom    09:00  → --news --news-gdelt"
  echo "Logs: ${LOG_DIR}/"
  crontab -l | grep "${MARKER}" || true
}

case "${1:-install}" in
  --uninstall|uninstall) uninstall ;;
  *) install ;;
esac
