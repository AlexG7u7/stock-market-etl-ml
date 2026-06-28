"""
CLI de paper trading BMV.

Comandos:
  python scripts/paper_trading.py init               — registra señales de signals_today.json
  python scripts/paper_trading.py status             — posiciones abiertas y pendientes
  python scripts/paper_trading.py settle             — cierra la semana con datos reales
  python scripts/paper_trading.py report             — scorecard acumulado completo
  python scripts/paper_trading.py history            — historial de trades cerrados
  python scripts/paper_trading.py cancel TICKER      — cancela una posición pendiente
  python scripts/paper_trading.py set-capital 50000  — cambia el capital inicial

Flujo recomendado:
  Viernes 21:00  → init      (después de generar señales)
  Viernes tarde  → settle    (cierra semana anterior si hay posiciones abiertas)
  Cualquier día  → status    (ver estado actual)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ml.paper_trading import (
    Journal, Trade, TradeEvent,
    load_signals_as_trades, settle_trade, compute_stats,
    DATA_DIR,
)

TICKERS_MX = {
    "WALMEX":"WALMEX.MX","FEMSAUBD":"FEMSAUBD.MX","GMEXICOB":"GMEXICOB.MX",
    "CEMEXCPO":"CEMEXCPO.MX","GFNORTEO":"GFNORTEO.MX","BIMBOA":"BIMBOA.MX",
    "ALSEA":"ALSEA.MX","KIMBERA":"KIMBERA.MX","PINFRA":"PINFRA.MX",
    "ORBIA":"ORBIA.MX","GRUMAB":"GRUMAB.MX","ASURB":"ASURB.MX",
    "OMAB":"OMAB.MX","GAPB":"GAPB.MX","GCARSOA1":"GCARSOA1.MX",
    "MEGACPO":"MEGACPO.MX","LABB":"LABB.MX","Q":"Q.MX","VOLARA":"VOLARA.MX",
}

# ─── Colores ANSI ─────────────────────────────────────────────────────────────
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"; C="\033[96m"; W="\033[0m"; BOLD="\033[1m"; GR="\033[90m"
def r(s): return f"{R}{s}{W}"
def g(s): return f"{G}{s}{W}"
def y(s): return f"{Y}{s}{W}"
def b(s): return f"{B}{s}{W}"
def c(s): return f"{C}{s}{W}"
def gr(s): return f"{GR}{s}{W}"
def bo(s): return f"{BOLD}{s}{W}"
def pnl_c(v): return g(f"+${v:,.0f}") if v >= 0 else r(f"-${abs(v):,.0f}")


# ─── INIT ─────────────────────────────────────────────────────────────────────

def cmd_init(journal: Journal, capital: float | None) -> None:
    if capital:
        journal.initial_capital = capital
        print(f"  Capital inicial: ${journal.initial_capital:,.0f} MXN")

    new_trades = load_signals_as_trades()
    added = 0
    for t in new_trades:
        before = len(journal.trades)
        journal.add_trade(t)
        if len(journal.trades) > before:
            added += 1
            print(f"  {g('+')} {bo(t.ticker):<12} P={t.p_up:.1%}  "
                  f"Entry=${t.entry_price:.2f}  Stop=${t.stop:.2f}  "
                  f"T1=${t.target_1:.2f}  T2=${t.target_2:.2f}  "
                  f"{t.shares_total} acc  ${t.capital_invested:,.0f} MXN")

    if added == 0:
        print(y("  Ya están registradas estas señales (sin duplicados)."))
    else:
        print(f"\n  {added} trade(s) añadidos al journal. Status: PENDING")
        print(gr("  Coloca las órdenes en GBM el lunes antes de las 8:30am."))

    journal.save()


# ─── STATUS ───────────────────────────────────────────────────────────────────

def cmd_status(journal: Journal) -> None:
    open_trades = journal.get_open()
    if not open_trades:
        print(gr("  Sin posiciones abiertas o pendientes."))
        return

    print(f"\n  {'TICKER':<12} {'ESTADO':<10} {'P_UP':>6} {'ENTRY':>8} {'STOP':>8} "
          f"{'T1':>8} {'T2':>8} {'PnL MXN':>10}")
    print(f"  {'─'*76}")
    for t in open_trades:
        state_str = (y(t.status) if t.status == "PENDING" else
                     c(t.status) if t.status == "OPEN" else
                     g(t.status))
        pnl = pnl_c(t.pnl_mxn) if t.status != "PENDING" else gr("—")
        print(f"  {bo(t.ticker):<12} {state_str:<10} {t.p_up:>5.1%} "
              f"${t.entry_price:>7.2f} ${t.stop_current:>7.2f} "
              f"${t.target_1:>7.2f} ${t.target_2:>7.2f} {pnl:>10}")
    print()

    stats = compute_stats(journal.trades, journal.initial_capital)
    if stats.get("n_closed", 0) > 0:
        pnl_total = stats["total_pnl"]
        print(f"  Trades cerrados: {stats['n_closed']}  |  Win rate: {stats['win_rate']}%  |  PnL total: {pnl_c(pnl_total)}")
    print()


# ─── SETTLE ───────────────────────────────────────────────────────────────────

def cmd_settle(journal: Journal) -> None:
    to_settle = [t for t in journal.trades if t.status in ("OPEN","PENDING","T1_HIT")]
    if not to_settle:
        print(gr("  No hay posiciones abiertas para cerrar."))
        return

    print(f"\n  Cerrando {len(to_settle)} posición(es) con datos reales...\n")

    for trade in to_settle:
        symbol = TICKERS_MX.get(trade.ticker, f"{trade.ticker}.MX")

        # Si es PENDING, buscar desde el lunes siguiente a la señal
        sig_date = datetime.strptime(trade.signal_date, "%Y-%m-%d")
        # Próximo lunes
        days_ahead = (7 - sig_date.weekday()) % 7
        if days_ahead == 0: days_ahead = 7
        entry_date  = sig_date + timedelta(days=days_ahead)
        end_date    = entry_date + timedelta(days=9)  # ~5 días hábiles + buffer

        try:
            raw = yf.download(
                symbol,
                start=entry_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d", auto_adjust=False, progress=False,
            )
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            # Solo los primeros 5 días hábiles
            ohlc = raw[["Open","High","Low","Close"]].dropna().head(5)

            if len(ohlc) == 0:
                print(y(f"  {trade.ticker}: sin datos para {entry_date.date()} — market cerrado o fin de datos"))
                continue

            print(f"  {bo(trade.ticker)} ({entry_date.date()} → {ohlc.index[-1].date()}, {len(ohlc)} días)...")

            settled = settle_trade(trade, ohlc)

            # Imprimir resultado
            for ev in settled.events:
                icon = "→" if ev.type=="ENTRY" else "✓" if ev.type in ("T1","T2") else "✗" if ev.type=="STOP" else "○"
                ev_pnl = pnl_c(ev.pnl_mxn) if ev.pnl_mxn != 0 else ""
                print(f"    {icon} {ev.date}  {ev.type:<7} @ ${ev.price:.2f}  {ev.shares:+d} acc  {ev_pnl}")

            status_str = (g(settled.status) if settled.status in ("T2_HIT","EXPIRED") and settled.pnl_mxn > 0
                          else r(settled.status) if settled.status == "STOP_HIT"
                          else c(settled.status))
            print(f"    → {status_str}  PnL: {pnl_c(settled.pnl_mxn)}  ({settled.pnl_pct:+.2f}%)\n")

        except Exception as e:
            print(r(f"  {trade.ticker}: error — {e}"))

    journal.update_equity(datetime.now().strftime("%Y-%m-%d"))
    journal.save()
    print("  Journal guardado.")


# ─── REPORT ───────────────────────────────────────────────────────────────────

def cmd_report(journal: Journal) -> None:
    stats = compute_stats(journal.trades, journal.initial_capital)
    closed = journal.get_closed()

    print(f"\n  {'═'*58}")
    print(f"  {'PAPER TRADING — SCORECARD':^58}")
    print(f"  Capital inicial: ${journal.initial_capital:,.0f} MXN")
    print(f"  {'═'*58}\n")

    if stats.get("n_closed", 0) == 0:
        print(gr("  Sin trades cerrados todavía.\n"))
        return

    pnl_str = pnl_c(stats["total_pnl"])
    print(f"  Trades totales:    {stats['n_closed']}")
    print(f"  Win rate:          {g(str(stats['win_rate'])+'%') if stats['win_rate'] >= 52 else y(str(stats['win_rate'])+'%')}")
    print(f"  PnL total:         {pnl_str}  ({stats['total_ret']:+.2f}%)")
    print(f"  Capital final:     ${stats['equity_final']:,.0f}")
    print(f"  Profit factor:     {stats['profit_factor']:.2f}")
    print(f"  Sharpe (anual):    {stats['sharpe']:.3f}")
    print(f"  Max drawdown:      {r(str(stats['max_drawdown'])+'%') if stats['max_drawdown'] > 3 else y(str(stats['max_drawdown'])+'%')}")
    print(f"  Avg win:           ${stats['avg_win']:,.0f}")
    print(f"  Avg loss:          ${stats['avg_loss']:,.0f}")
    print(f"\n  Por resultado:")
    print(f"    T2 (objetivo 2): {stats['n_t2_hits']} trades  {g('✓')}")
    print(f"    Stop hit:        {stats['n_stops']}  trades  {r('✗')}")
    print(f"    Expirados:       {stats['n_expired']} trades")

    # Modelo: ¿las predicciones fueron correctas?
    model_checked = [t for t in journal.trades if t.model_correct is not None]
    if model_checked:
        correct = sum(1 for t in model_checked if t.model_correct)
        print(f"\n  Calibración del modelo:")
        print(f"    Predicciones verificadas: {len(model_checked)}")
        print(f"    Precio subió en 5d: {correct}/{len(model_checked)} = {correct/len(model_checked)*100:.1f}%")
        print(f"    Modelo esperaba: {sum(t.p_up for t in model_checked)/len(model_checked)*100:.1f}% promedio")

    print()


# ─── HISTORY ─────────────────────────────────────────────────────────────────

def cmd_history(journal: Journal) -> None:
    closed = journal.get_closed()
    if not closed:
        print(gr("  Sin trades cerrados."))
        return

    print(f"\n  {'#':<3} {'TICKER':<12} {'SEÑAL':<12} {'ENTRADA':<12} {'ESTADO':<10} {'P_UP':>5} {'PnL MXN':>10} {'PnL%':>7}")
    print(f"  {'─'*72}")
    for i, t in enumerate(sorted(closed, key=lambda x: x.exit_date or ""), 1):
        status_str = (g(t.status) if t.pnl_mxn > 0 else r(t.status))
        print(f"  {i:<3} {bo(t.ticker):<12} {t.signal_date:<12} {(t.entry_date or '—'):<12} "
              f"{status_str:<10} {t.p_up:>4.0%} {pnl_c(t.pnl_mxn):>10} {t.pnl_pct:>+6.2f}%")
    print()


# ─── CANCEL ───────────────────────────────────────────────────────────────────

def cmd_cancel(journal: Journal, ticker: str) -> None:
    for t in journal.trades:
        if t.ticker.upper() == ticker.upper() and t.status == "PENDING":
            t.status = "CANCELLED"
            journal.save()
            print(y(f"  {ticker} cancelado."))
            return
    print(r(f"  {ticker} no encontrado en posiciones PENDING."))


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Paper Trading BMV")
    sub    = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init",   help="Registrar señales actuales")
    p_init.add_argument("--capital", type=float, default=None)

    sub.add_parser("status",  help="Ver posiciones abiertas")
    sub.add_parser("settle",  help="Cerrar semana con datos reales")
    sub.add_parser("report",  help="Scorecard acumulado")
    sub.add_parser("history", help="Historial de trades cerrados")

    p_cancel = sub.add_parser("cancel", help="Cancelar posición pendiente")
    p_cancel.add_argument("ticker")

    p_cap = sub.add_parser("set-capital", help="Cambiar capital inicial")
    p_cap.add_argument("amount", type=float)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    journal = Journal()

    if args.cmd == "init":
        cmd_init(journal, getattr(args, "capital", None))
    elif args.cmd == "status":
        cmd_status(journal)
    elif args.cmd == "settle":
        cmd_settle(journal)
    elif args.cmd == "report":
        cmd_report(journal)
    elif args.cmd == "history":
        cmd_history(journal)
    elif args.cmd == "cancel":
        cmd_cancel(journal, args.ticker)
    elif args.cmd == "set-capital":
        journal.initial_capital = args.amount
        journal.save()
        print(g(f"  Capital ajustado a ${args.amount:,.0f} MXN"))

if __name__ == "__main__":
    main()
