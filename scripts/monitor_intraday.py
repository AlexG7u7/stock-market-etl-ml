"""
Monitor intraday BMV — alertas automáticas de precio.

Carga las posiciones de data/signals_today.json y monitorea en tiempo real:
  ► STOP HIT  — precio cae por debajo del stop        → notificación + cerrar
  ► T1 HIT    — precio llega al primer objetivo        → notificación + mover stop a breakeven
  ► T2 HIT    — precio llega al segundo objetivo       → notificación + cerrar
  ► PULLBACK  — posición abre verde pero se reversa    → advertencia temprana
  ► STALE     — acción no se movió en 2+ días         → revisión

Salida:
  - Terminal con colores + tabla de estado actualizada
  - Notificaciones macOS (display notification)
  - data/monitor_state.json — estado actual de cada posición
  - data/monitor_log.jsonl  — historial de alertas

Ejecución:
    python scripts/monitor_intraday.py                     # carga signals_today.json
    python scripts/monitor_intraday.py --interval 2        # poll cada 2 min
    python scripts/monitor_intraday.py --once              # correr una vez y salir

Horario BMV: 8:30–15:00 hora del centro de México (UTC-6)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─── Zona horaria y horario de mercado ───────────────────────────────────────
TZ_MX      = ZoneInfo("America/Mexico_City")
MARKET_OPEN  = (8, 30)
MARKET_CLOSE = (15,  0)

# ─── ANSI colores ────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m";  BOLD   = "\033[1m"
    RED    = "\033[91m"; GREEN  = "\033[92m"
    YELLOW = "\033[93m"; BLUE   = "\033[94m"
    CYAN   = "\033[96m"; GREY   = "\033[90m"
    BG_RED = "\033[41m"; BG_GRN = "\033[42m"

def red(s):    return f"{C.RED}{s}{C.RESET}"
def green(s):  return f"{C.GREEN}{s}{C.RESET}"
def yellow(s): return f"{C.YELLOW}{s}{C.RESET}"
def bold(s):   return f"{C.BOLD}{s}{C.RESET}"
def grey(s):   return f"{C.GREY}{s}{C.RESET}"
def cyan(s):   return f"{C.CYAN}{s}{C.RESET}"


# ─── Notificación macOS ───────────────────────────────────────────────────────
def notify_mac(title: str, message: str, sound: str = "Glass") -> None:
    """Notificación nativa de macOS vía osascript."""
    script = (
        f'display notification "{message}" '
        f'with title "{title}" '
        f'sound name "{sound}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    except Exception:
        pass


# ─── Estado de posición ───────────────────────────────────────────────────────
STATES = ("OPEN", "T1_HIT", "T2_HIT", "STOP_HIT", "EXPIRED", "CANCELLED")

def make_position(sig: dict) -> dict:
    return {
        "ticker":       sig["ticker"],
        "entry":        sig["entry"],
        "stop":         sig["stop"],
        "stop_current": sig["stop"],          # se mueve a breakeven en T1
        "target_1":     sig["target_1"],
        "target_2":     sig["target_2"],
        "shares":       sig["shares"],
        "capital_mxn":  sig["capital_mxn"],
        "pct_capital":  sig["pct_capital"],
        "p_up":         sig.get("p_up", 0.0),
        "state":        "OPEN",
        "price_last":   sig["price"],
        "price_high":   sig["price"],         # high water mark
        "pnl_mxn":      0.0,
        "pnl_pct":      0.0,
        "t1_units":     sig["shares"],        # acciones restantes post-T1
        "alert_log":    [],
        "opened_at":    datetime.now(TZ_MX).isoformat(),
        "closed_at":    None,
    }


# ─── Fetch precio actual (1 min / 5 min intraday) ────────────────────────────

TICKERS_MX: dict[str, str] = {
    "WALMEX":   "WALMEX.MX",   "FEMSAUBD": "FEMSAUBD.MX",
    "GMEXICOB": "GMEXICOB.MX", "CEMEXCPO": "CEMEXCPO.MX",
    "GFNORTEO": "GFNORTEO.MX", "BIMBOA":   "BIMBOA.MX",
    "ALSEA":    "ALSEA.MX",    "KIMBERA":  "KIMBERA.MX",
    "PINFRA":   "PINFRA.MX",   "ORBIA":    "ORBIA.MX",
    "GRUMAB":   "GRUMAB.MX",   "ASURB":    "ASURB.MX",
    "OMAB":     "OMAB.MX",     "GAPB":     "GAPB.MX",
    "GCARSOA1": "GCARSOA1.MX", "MEGACPO":  "MEGACPO.MX",
    "LABB":     "LABB.MX",     "Q":        "Q.MX",
    "VOLARA":   "VOLARA.MX",
}


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """
    Descarga el precio más reciente de cada ticker.
    Usa interval='2m' period='1d' para datos intraday de hoy.
    Fallback a 'close' del día si falla el intraday.
    """
    prices: dict[str, float] = {}
    symbols = [TICKERS_MX.get(t, f"{t}.MX") for t in tickers]

    try:
        raw = yf.download(
            " ".join(symbols),
            period="1d", interval="2m",
            auto_adjust=False, progress=False,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]] if len(symbols) == 1 else raw

        for t, sym in zip(tickers, symbols):
            col = sym if sym in close.columns else close.columns[0] if len(symbols) == 1 else None
            if col and col in close.columns:
                last = close[col].dropna()
                if len(last) > 0:
                    prices[t] = float(last.iloc[-1])
    except Exception as e:
        print(grey(f"  [fetch] error intraday: {e}"))

    # Fallback: daily close para los que fallaron
    missing = [t for t in tickers if t not in prices]
    if missing:
        syms = [TICKERS_MX.get(t, f"{t}.MX") for t in missing]
        try:
            raw2 = yf.download(" ".join(syms), period="5d", interval="1d",
                               auto_adjust=False, progress=False)
            if isinstance(raw2.columns, pd.MultiIndex):
                c2 = raw2["Close"]
            else:
                c2 = raw2[["Close"]]
            for t, sym in zip(missing, syms):
                col = sym if sym in c2.columns else c2.columns[0] if len(missing)==1 else None
                if col and col in c2.columns:
                    last = c2[col].dropna()
                    if len(last) > 0:
                        prices[t] = float(last.iloc[-1])
        except Exception:
            pass

    return prices


# ─── Motor de alertas ─────────────────────────────────────────────────────────

def check_position(pos: dict, price: float, now: datetime) -> list[dict]:
    """
    Evalúa el estado de una posición dado el precio actual.
    Devuelve lista de alertas generadas.
    """
    alerts: list[dict] = []
    state  = pos["state"]

    if state in ("T2_HIT", "STOP_HIT", "EXPIRED", "CANCELLED"):
        return alerts   # posición ya cerrada

    entry   = pos["entry"]
    stop    = pos["stop_current"]
    t1      = pos["target_1"]
    t2      = pos["target_2"]
    units   = pos["t1_units"]

    # Actualizar precio y high water mark
    pos["price_last"] = price
    pos["price_high"] = max(pos["price_high"], price)

    # PnL con unidades actuales
    pos["pnl_pct"] = round((price - entry) / entry * 100, 3)
    pos["pnl_mxn"] = round((price - entry) * units, 2)

    def alert(level: str, msg: str, sound: str = "Glass") -> dict:
        a = {
            "time":   now.isoformat(),
            "ticker": pos["ticker"],
            "level":  level,
            "price":  price,
            "msg":    msg,
        }
        alerts.append(a)
        pos["alert_log"].append(a)
        notify_mac(f"BMV · {pos['ticker']} · {level}", msg, sound=sound)
        return a

    # ── STOP HIT ──────────────────────────────────────────────────────────────
    if price <= stop:
        pnl = (price - entry) * units
        alert("STOP_HIT",
              f"Stop activado @ ${price:.2f}  (Stop={stop:.2f})  "
              f"PnL={pnl:+,.0f} MXN",
              sound="Sosumi")
        pos["state"]     = "STOP_HIT"
        pos["closed_at"] = now.isoformat()
        pos["pnl_mxn"]   = round(pnl, 2)
        return alerts

    # ── T2 HIT ────────────────────────────────────────────────────────────────
    if price >= t2 and state in ("OPEN", "T1_HIT"):
        pnl = (price - entry) * units
        alert("T2_HIT",
              f"Objetivo 2 alcanzado @ ${price:.2f}  (T2={t2:.2f})  "
              f"PnL={pnl:+,.0f} MXN  ✅ Cerrar todo",
              sound="Hero")
        pos["state"]     = "T2_HIT"
        pos["closed_at"] = now.isoformat()
        pos["pnl_mxn"]   = round(pnl, 2)
        return alerts

    # ── T1 HIT (solo si no lo habíamos marcado antes) ─────────────────────────
    if price >= t1 and state == "OPEN":
        half = pos["shares"] // 2
        pnl_partial = (price - entry) * half
        alert("T1_HIT",
              f"Objetivo 1 @ ${price:.2f}  (T1={t1:.2f})  "
              f"Vender {half} acc  PnL parcial={pnl_partial:+,.0f} MXN",
              sound="Ping")
        pos["state"]        = "T1_HIT"
        pos["t1_units"]     = pos["shares"] - half
        pos["stop_current"] = round(entry, 2)   # mover stop a breakeven

    # ── PULLBACK WARNING — cerró sobre T1 pero reversa ─────────────────────────
    if state == "T1_HIT" and price < entry * 1.005:
        alert("PULLBACK",
              f"Pullback: posición T1 hit volvió a entrada @ ${price:.2f}  "
              f"(BE={entry:.2f})  Vigilar stop",
              sound="Bottle")

    return alerts


# ─── Persistencia ─────────────────────────────────────────────────────────────

STATE_FILE = ROOT / "data" / "monitor_state.json"
LOG_FILE   = ROOT / "data" / "monitor_log.jsonl"


def load_state() -> list[dict]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return []


def save_state(positions: list[dict]) -> None:
    STATE_FILE.write_text(json.dumps(positions, indent=2, ensure_ascii=False))


def append_log(alerts: list[dict]) -> None:
    with LOG_FILE.open("a") as f:
        for a in alerts:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")


def load_signals() -> list[dict]:
    sig_file = ROOT / "data" / "signals_today.json"
    if not sig_file.exists():
        print(red("ERROR: data/signals_today.json no encontrado. Corre primero generate_signals.py"))
        sys.exit(1)
    data = json.loads(sig_file.read_text())
    return data.get("signals", [])


# ─── Impresión de estado ──────────────────────────────────────────────────────

def state_color(state: str) -> str:
    if state == "OPEN":     return cyan(state)
    if state == "T1_HIT":  return green(state)
    if state == "T2_HIT":  return f"{C.BG_GRN}{C.BOLD} T2 ✅ {C.RESET}"
    if state == "STOP_HIT":return f"{C.BG_RED}{C.BOLD} STOP 🔴 {C.RESET}"
    if state == "EXPIRED":  return grey(state)
    return grey(state)


def pnl_str(pnl_pct: float, pnl_mxn: float) -> str:
    s = f"{pnl_pct:+.2f}%  ${pnl_mxn:+,.0f}"
    return green(s) if pnl_pct >= 0 else red(s)


def print_status(positions: list[dict], now: datetime, prices: dict[str, float]) -> None:
    print(f"\n{'─'*78}")
    print(f"  {bold('MONITOR BMV')}  |  {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'─'*78}")
    fmt = "  {:<11} {:>8} {:>8} {:>8} {:>8}  {:>12}  {}"
    print(fmt.format("TICKER", "PRECIO", "ENTRY", "STOP", "T1/T2", "PnL", "ESTADO"))
    print(f"  {'─'*72}")

    open_count = 0
    total_pnl  = 0.0

    for pos in positions:
        t      = pos["ticker"]
        px     = prices.get(t, pos["price_last"])
        state  = pos["state"]
        if state == "OPEN": open_count += 1

        lvl = f"{pos['target_1']:.2f}/{pos['target_2']:.2f}"
        if state == "T1_HIT":
            lvl = yellow(f"T1✓ {pos['target_2']:.2f}")

        pnl_pct = (px - pos["entry"]) / pos["entry"] * 100
        pnl_mxn = (px - pos["entry"]) * pos["t1_units"]
        total_pnl += pnl_mxn

        print(fmt.format(
            bold(t),
            f"${px:.2f}",
            f"${pos['entry']:.2f}",
            f"${pos['stop_current']:.2f}",
            lvl,
            pnl_str(pnl_pct, pnl_mxn),
            state_color(state),
        ))

    print(f"  {'─'*72}")
    color_total = green if total_pnl >= 0 else red
    print(f"  {bold('Total PnL:'):>38} {color_total(f'${total_pnl:+,.0f} MXN')}")
    print(f"  {grey('Posiciones abiertas: ' + str(open_count))}")
    print()


# ─── Loop principal ────────────────────────────────────────────────────────────

def is_market_open(now: datetime) -> bool:
    h, m = now.hour, now.minute
    open_mins  = MARKET_OPEN[0]  * 60 + MARKET_OPEN[1]
    close_mins = MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]
    current    = h * 60 + m
    return open_mins <= current <= close_mins and now.weekday() < 5


def run_monitor(interval_min: int = 5, once: bool = False) -> None:
    print(bold(cyan("\n  ╔══════════════════════════════════════════════════╗")))
    print(bold(cyan(  "  ║   MONITOR INTRADAY BMV — Risk Engine activo     ║")))
    print(bold(cyan(  "  ╚══════════════════════════════════════════════════╝\n")))

    # ── Cargar o inicializar posiciones ──────────────────────────────────────
    saved = load_state()
    if saved:
        print(f"  Cargando {len(saved)} posiciones guardadas desde monitor_state.json")
        positions = saved
    else:
        signals   = load_signals()
        positions = [make_position(s) for s in signals]
        print(f"  Inicializando {len(positions)} posiciones desde signals_today.json")
        save_state(positions)

    if not positions:
        print(red("  No hay posiciones activas. Corre generate_signals.py primero."))
        return

    active_tickers = [p["ticker"] for p in positions]
    print(f"  Posiciones: {', '.join(active_tickers)}")
    print(f"  Polling cada {interval_min} min · Ctrl+C para parar\n")

    while True:
        now = datetime.now(TZ_MX)

        if not is_market_open(now) and not once:
            next_msg = "fuera de horario BMV (8:30–15:00 CT)"
            remaining = [p for p in positions if p["state"] in ("OPEN","T1_HIT")]
            if not remaining:
                print(green("  Todas las posiciones cerradas. Monitor terminado."))
                break
            print(grey(f"  {now.strftime('%H:%M')} — {next_msg} — {len(remaining)} posiciones abiertas"))
            if once:
                break
            time.sleep(60)
            continue

        # ── Fetch precios ─────────────────────────────────────────────────────
        watching = [p["ticker"] for p in positions if p["state"] in ("OPEN","T1_HIT")]
        if not watching:
            print(green("  Todas las posiciones cerradas. "))
            break

        prices = fetch_prices(watching)

        # ── Evaluar alertas ───────────────────────────────────────────────────
        all_alerts: list[dict] = []
        for pos in positions:
            if pos["ticker"] not in prices:
                continue
            new_alerts = check_position(pos, prices[pos["ticker"]], now)
            all_alerts.extend(new_alerts)

        # ── Imprimir y guardar ────────────────────────────────────────────────
        print_status(positions, now, prices)

        if all_alerts:
            print(f"  {bold('🔔 ALERTAS:')}")
            for a in all_alerts:
                level_str = (red if "STOP" in a["level"] else
                             green if "T2" in a["level"] else
                             yellow)(f"  [{a['level']}] {a['ticker']} @ ${a['price']:.2f}: {a['msg']}")
                print(level_str)
            print()

        if all_alerts:
            append_log(all_alerts)
        save_state(positions)

        # Verificar expiración (5 días desde apertura)
        for pos in positions:
            if pos["state"] in ("OPEN","T1_HIT"):
                opened = datetime.fromisoformat(pos["opened_at"])
                if (now - opened).days >= 5:
                    pos["state"]     = "EXPIRED"
                    pos["closed_at"] = now.isoformat()
                    notify_mac(f"BMV · {pos['ticker']}", "Posición expirada (5 días). Cerrar manualmente.")
                    print(yellow(f"  [EXPIRED] {pos['ticker']} — 5 días cumplidos"))

        if once:
            break

        time.sleep(interval_min * 60)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor intraday BMV")
    parser.add_argument("--interval", type=int, default=5,
                        help="Minutos entre consultas (default 5)")
    parser.add_argument("--once", action="store_true",
                        help="Ejecutar una sola vez y salir (útil para testing)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignorar state guardado y recargar signals_today.json")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print(yellow("  State reseteado."))

    run_monitor(interval_min=args.interval, once=args.once)


if __name__ == "__main__":
    main()
