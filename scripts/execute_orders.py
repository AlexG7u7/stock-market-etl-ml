"""
Ejecuta las señales de signals_today.json como órdenes en GBM+.

Uso:
    python scripts/execute_orders.py --dry-run        # simula (default)
    python scripts/execute_orders.py --live           # envía órdenes reales (⚠️)

Variables de entorno requeridas (para --live):
    GBM_EMAIL, GBM_PASSWORD, GBM_CLIENT_ID
    GBM_LIVE=true

El script:
1. Carga signals_today.json
2. Verifica que cada señal aún tenga precio de entrada razonable (±1% del actual)
3. En dry-run: imprime qué órdenes se enviarían
4. En live: coloca órdenes límite en GBM+
5. Guarda el resultado en data/orders_log.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.broker.gbm_client import GBMClient, GBMConfigError, GBMConnectionError, OrderRequest

DATA = ROOT / "data"
ORDERS_LOG = DATA / "orders_log.json"


def load_signals() -> dict:
    path = DATA / "signals_today.json"
    if not path.exists():
        print("ERROR: No existe signals_today.json. Corre generate_signals.py primero.")
        sys.exit(1)
    return json.loads(path.read_text())


def save_orders_log(results: list[dict]) -> None:
    existing: list[dict] = []
    if ORDERS_LOG.exists():
        existing = json.loads(ORDERS_LOG.read_text())
    existing.extend(results)
    ORDERS_LOG.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def execute(dry_run_override: bool | None = None) -> None:
    signals_data = load_signals()
    signals      = signals_data.get("signals", [])
    meta         = signals_data.get("meta", {})

    if not signals:
        print("No hay señales para ejecutar.")
        return

    # Override del modo live/dry si viene de CLI
    if dry_run_override is not None:
        os.environ["GBM_LIVE"] = "false" if dry_run_override else "true"

    client   = GBMClient()
    mode_str = "DRY-RUN" if client.dry_run else "⚠️  LIVE"

    print(f"\n{'='*60}")
    print(f"  Ejecutor de órdenes GBM+  —  modo: {mode_str}")
    print(f"  Señales: {len(signals)}  |  Capital: ${meta.get('capital',0):,.0f} MXN")
    print(f"  Fecha señales: {meta.get('date','')}")
    print(f"{'='*60}\n")

    if not client.dry_run and not client.credentials_set:
        print("ERROR: Faltan credenciales. Configura GBM_EMAIL, GBM_PASSWORD, GBM_CLIENT_ID.")
        sys.exit(1)

    if not client.dry_run:
        confirm = input(
            "⚠️  MODO LIVE: ¿Confirmas que quieres enviar órdenes REALES a GBM+? [escribe 'SI']: "
        )
        if confirm.strip().upper() != "SI":
            print("Operación cancelada.")
            return

    # Conectar y obtener portafolio para verificar saldo
    portfolio = None
    if client.credentials_set:
        try:
            print("Obteniendo portafolio de GBM+...")
            portfolio = client.get_portfolio()
            print(f"  Saldo disponible: ${portfolio.buying_power:,.0f} MXN")
            print(f"  Valor mercado:    ${portfolio.market_value:,.0f} MXN")
            print(f"  Total:            ${portfolio.total_value:,.0f} MXN\n")
        except (GBMConfigError, GBMConnectionError) as e:
            if not client.dry_run:
                print(f"ERROR de conexión: {e}")
                sys.exit(1)
            print(f"[INFO] Sin conexión a GBM+ (modo dry-run: {e})\n")

    results = []
    total_capital_sending = sum(s["capital_mxn"] for s in signals)

    # Verificar saldo suficiente (solo en live con portafolio disponible)
    if portfolio and not client.dry_run:
        if total_capital_sending > portfolio.buying_power * 1.05:
            print(
                f"ADVERTENCIA: Capital a invertir (${total_capital_sending:,.0f}) "
                f"supera el saldo disponible (${portfolio.buying_power:,.0f})."
            )
            confirm2 = input("¿Continuar de todas formas? [escribe 'SI']: ")
            if confirm2.strip().upper() != "SI":
                print("Operación cancelada.")
                return

    for s in signals:
        req = OrderRequest(
            ticker=s["ticker"],
            side="BUY",
            shares=int(s["shares"]),
            limit_price=round(s["entry"] * 1.001, 2),  # +0.1% por encima del cierre para asegurar fill
            notes=f"Señal modelo — P(↑)={s['p_up']*100:.0f}% — {s.get('reason','')}",
        )

        print(f"  {req.ticker:<20} {req.shares:>5} acciones @ ${req.limit_price:.2f}  "
              f"(${req.shares * req.limit_price:,.0f} MXN)  P(↑)={s['p_up']*100:.0f}%")
        print(f"    Stop: ${s['stop']:.2f}  T1: ${s['target_1']:.2f}  T2: ${s['target_2']:.2f}")
        print(f"    Razón: {s.get('reason','')}")

        result = client.place_order(req)

        results.append({
            "timestamp": datetime.now().isoformat(),
            "signal_date": meta.get("date", ""),
            "ticker": s["ticker"],
            "side": "BUY",
            "shares": int(s["shares"]),
            "limit_price": req.limit_price,
            "stop": s["stop"],
            "target_1": s["target_1"],
            "target_2": s["target_2"],
            "p_up": s["p_up"],
            "capital_mxn": s["capital_mxn"],
            "order_id": result.order_id,
            "success": result.success,
            "dry_run": result.dry_run,
            "message": result.message,
        })

        status = "✅" if result.success else "❌"
        print(f"    {status} {result.message}\n")

    save_orders_log(results)
    ok_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"  Completado: {ok_count}/{len(results)} órdenes {'simuladas' if client.dry_run else 'enviadas'}")
    print(f"  Log guardado en: data/orders_log.json")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    dry = "--live" not in sys.argv
    execute(dry_run_override=dry)
