"""
Screener BMV — señales para operar el lunes
============================================
Descarga ~90 días de datos de los tickers más líquidos del IPC,
calcula indicadores técnicos y genera un ranking de señales.

Uso:
    python scripts/screener_lunes.py

Salida:
    - Tabla en terminal
    - JSON en data/screener_output.json  (para el canvas)
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ─── Universo de tickers IPC más líquidos ────────────────────────────────────
TICKERS = {
    "WALMEX": "WALMEX.MX",
    "AMXL": "AMXL.MX",
    "FEMSAUBD": "FEMSAUBD.MX",
    "GMEXICOB": "GMEXICOB.MX",
    "CEMEXCPO": "CEMEXCPO.MX",
    "GFNORTEO": "GFNORTEO.MX",
    "BIMBOA": "BIMBOA.MX",
    "ALSEA": "ALSEA.MX",
    "KIMBERA": "KIMBERA.MX",
    "PINFRA": "PINFRA.MX",
    "ORBIA": "ORBIA.MX",
    "GRUMAB": "GRUMAB.MX",
    "ASURB": "ASURB.MX",
    "OMAB": "OMAB.MX",
    "GAPB": "GAPB.MX",
    "GCARSOA1": "GCARSOA1.MX",
    "MEGACPO": "MEGACPO.MX",
    "LABB": "LABB.MX",
    "Q": "Q.MX",
    "VOLARA": "VOLARA.MX",
    "NAFTRAC": "NAFTRAC.MX",   # ETF del IPC como referencia
}

# ─── Indicadores técnicos ─────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - 100 / (1 + rs)
    return float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan


def analyze(ticker_name: str, yahoo_symbol: str, days: int = 90) -> dict | None:
    end = datetime.today()
    start = end - timedelta(days=days)
    try:
        df = yf.download(
            yahoo_symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=False,
            progress=False,
            actions=False,
        )
    except Exception as e:
        print(f"  [ERROR] {ticker_name}: {e}", file=sys.stderr)
        return None

    # Flatten multi-level columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty or len(df) < 20:
        print(f"  [SKIP]  {ticker_name}: sin datos suficientes", file=sys.stderr)
        return None

    close = df["Close"].dropna()
    volume = df["Volume"].dropna()

    if len(close) < 20:
        return None

    # ── Precio y retornos ──
    price_now = float(close.iloc[-1])
    price_1w_ago = float(close.iloc[-6]) if len(close) >= 6 else price_now
    price_1m_ago = float(close.iloc[-22]) if len(close) >= 22 else price_now

    ret_1d = float(close.pct_change().iloc[-1]) * 100
    ret_1w = (price_now / price_1w_ago - 1) * 100
    ret_1m = (price_now / price_1m_ago - 1) * 100

    # ── Medias móviles ──
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else np.nan

    # ── RSI ──
    rsi_val = rsi(close, 14)

    # ── Posición relativa al rango 52 semanas ──
    high_52w = float(close.rolling(min(252, len(close))).max().iloc[-1])
    low_52w = float(close.rolling(min(252, len(close))).min().iloc[-1])
    pos_52w = (price_now - low_52w) / (high_52w - low_52w + 1e-8) * 100

    # ── Volumen relativo (hoy vs promedio 20d) ──
    vol_now = float(volume.iloc[-1]) if len(volume) > 0 else 0
    vol_avg20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else 1
    vol_ratio = vol_now / vol_avg20 if vol_avg20 > 0 else 1.0

    # ── Señal compuesta (0-100) ──
    score = 0.0
    signals = []

    # RSI: oversold=compra, overbought=venta
    if not np.isnan(rsi_val):
        if rsi_val < 35:
            score += 25
            signals.append("RSI oversold")
        elif rsi_val < 45:
            score += 15
            signals.append("RSI bajo")
        elif rsi_val > 65:
            score -= 10
            signals.append("RSI alto")

    # Precio sobre SMA20 = tendencia alcista
    if price_now > sma20:
        score += 20
        signals.append("Sobre SMA20")
    else:
        score -= 10
        signals.append("Bajo SMA20")

    # SMA20 sobre SMA50 = golden cross region
    if not np.isnan(sma50):
        if sma20 > sma50:
            score += 15
            signals.append("SMA20 > SMA50")
        else:
            score -= 5

    # Momentum 1 semana positivo
    if ret_1w > 2:
        score += 15
        signals.append(f"Mom+1S {ret_1w:.1f}%")
    elif ret_1w < -3:
        score -= 10
        signals.append(f"Mom-1S {ret_1w:.1f}%")

    # Volumen relativo alto = confirmación
    if vol_ratio > 1.5:
        score += 10
        signals.append(f"Vol x{vol_ratio:.1f}")

    # Posición 52w — no comprar cerca de máximos sin momentum
    if pos_52w > 90:
        score -= 5
        signals.append("Cerca máx 52s")
    elif pos_52w < 20:
        score += 10
        signals.append("Cerca mín 52s")

    # ── Dirección de señal ──
    if score >= 40:
        direction = "COMPRA"
    elif score >= 20:
        direction = "VIGILAR"
    elif score <= -10:
        direction = "EVITAR"
    else:
        direction = "NEUTRO"

    return {
        "ticker": ticker_name,
        "price": round(price_now, 2),
        "ret_1d": round(ret_1d, 2),
        "ret_1w": round(ret_1w, 2),
        "ret_1m": round(ret_1m, 2),
        "rsi": round(rsi_val, 1) if not np.isnan(rsi_val) else None,
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2) if not np.isnan(sma50) else None,
        "vol_ratio": round(vol_ratio, 2),
        "pos_52w": round(pos_52w, 1),
        "score": round(score, 1),
        "direction": direction,
        "signals": signals,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*65}")
    print(f"  SCREENER BMV — {datetime.now().strftime('%A %d %b %Y %H:%M')}")
    print(f"{'='*65}\n")

    results = []
    for name, symbol in TICKERS.items():
        print(f"  Descargando {name} ({symbol})...")
        rec = analyze(name, symbol)
        if rec:
            results.append(rec)

    if not results:
        print("\n[ERROR] No se obtuvieron datos. Verifica tu conexión.")
        sys.exit(1)

    # Ordenar por score descendente
    results.sort(key=lambda x: x["score"], reverse=True)

    # ── Tabla terminal ──
    print(f"\n{'─'*90}")
    print(f"  {'TICKER':<12} {'PRECIO':>8} {'1D%':>6} {'1W%':>6} {'RSI':>5} {'POS52W':>7} {'SCORE':>6}  SEÑAL")
    print(f"{'─'*90}")
    for r in results:
        rsi_str = f"{r['rsi']:.0f}" if r['rsi'] else "—"
        direction_icon = {"COMPRA": ">>", "VIGILAR": "->", "NEUTRO": "  ", "EVITAR": "xx"}.get(r["direction"], "  ")
        print(
            f"  {r['ticker']:<12} {r['price']:>8.2f} "
            f"{r['ret_1d']:>+6.2f} {r['ret_1w']:>+6.2f} "
            f"{rsi_str:>5} {r['pos_52w']:>6.0f}% "
            f"{r['score']:>6.0f}  {direction_icon} {r['direction']}"
        )
        print(f"  {'':>12}   Señales: {', '.join(r['signals'])}")
    print(f"{'─'*90}\n")

    # ── Guardar JSON para el canvas ──
    out_path = Path(__file__).parent.parent / "data" / "screener_output.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Guardado en: {out_path}\n")


if __name__ == "__main__":
    main()
