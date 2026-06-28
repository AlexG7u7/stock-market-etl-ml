#!/bin/zsh
# Actualización diaria automática del pipeline BMV
# Corre: lunes–viernes a las 16:00 hora de Ciudad de México
#
# Para instalar:
#   crontab -e
#   Agregar la línea del crontab que está al final de este archivo

PROJECT="/Users/rod/Projects/stock-market"
LOG="$PROJECT/logs/daily_update.log"
VENV="$PROJECT/venv/bin/activate"

mkdir -p "$PROJECT/logs"
echo "──────────────────────────────────────" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Inicio" >> "$LOG"

# Activar entorno virtual
source "$VENV"

# 1. Actualizar base de datos (solo días nuevos, ~5 segundos)
echo "$(date '+%H:%M:%S') Actualizando BD..." >> "$LOG"
python "$PROJECT/scripts/build_database.py" --update >> "$LOG" 2>&1

# 2. Regenerar señales (solo viernes)
DOW=$(date '+%u')   # 1=lunes … 5=viernes
if [ "$DOW" -eq 5 ]; then
    echo "$(date '+%H:%M:%S') Generando señales (viernes)..." >> "$LOG"
    python "$PROJECT/scripts/generate_signals.py" --capital 100000 >> "$LOG" 2>&1

    # 3. Registrar en paper trading
    python "$PROJECT/scripts/paper_trading.py" init >> "$LOG" 2>&1

    # 4. Notificación macOS
    osascript -e 'display notification "Señales BMV listas. Abre signals-today canvas." with title "BMV — Viernes" sound name "Glass"' 2>/dev/null
fi

echo "$(date '+%H:%M:%S') Fin." >> "$LOG"

# ─── CRONTAB (pegar en `crontab -e`) ─────────────────────────────────────────
# Corre lun–vie a las 16:00 hora local (después del cierre BMV 15:00 CT)
#
# 0 16 * * 1-5 /Users/rod/Projects/stock-market/scripts/daily_update.sh
