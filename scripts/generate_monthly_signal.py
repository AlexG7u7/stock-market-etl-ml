"""
Señal mensual de inversión — corre el primer lunes de cada mes.

Genera el ranking top-5 de acciones BMV con:
  - Score del modelo (percentil predicho 0-1)
  - Las 3 razones principales por las que está en el top
  - Indicador de régimen del mercado
  - Plan de acción: qué comprar, cuánto, cuándo rotar
  - Guarda JSON en data/monthly_signal.json para el dashboard

Uso:
    python scripts/generate_monthly_signal.py
    python scripts/generate_monthly_signal.py --capital 50000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store  import get as store_get, BMV_TICKERS, MACRO_TICKERS
from src.ml.features import (compute_features, add_macro_features,
                             add_cross_section_features, compute_target, FEATURE_COLS)
from scripts.cross_sectional_v2 import add_rank_normalized, RN_COLS, _LGBM_BASE
from scripts.cross_sectional_backtest import build_cross_sectional

HORIZON   = 20
TOP_N     = 5
OUT_PATH  = ROOT / "data" / "monthly_signal.json"

# Nombres legibles de las features más importantes
FEAT_LABELS = {
    "rn_cs_mom_rank":    "Momentum relativo al universo",
    "rn_ret_20d":        "Retorno último mes vs pares",
    "rn_ret_5d":         "Retorno última semana vs pares",
    "rn_cs_ret5_rank":   "Posición de momentum 5d en el ranking",
    "rn_cs_ret20_rank":  "Posición de momentum 20d en el ranking",
    "rn_vol_ratio_20":   "Volumen inusualmente alto (interés del mercado)",
    "rn_obv_slope":      "Dinero acumulándose (OBV trend)",
    "rn_cs_vol_rank":    "Actividad de volumen vs el universo",
    "rn_rsi_14":         "RSI relativo — posición de sobrecompra/venta",
    "rn_bb_pct":         "Posición en Bollinger vs pares",
    "rn_mkt_trend":      "Tendencia del mercado IPC",
    "rn_sp500_ret5":     "Impulso de Wall Street",
    "rn_usdmxn_ret5":    "Movimiento del peso (USD/MXN)",
    "rn_atr_pct":        "Volatilidad relativa",
    "rn_price_vs_sma20": "Precio vs media 20d relativa al universo",
    "rn_price_vs_sma50": "Precio vs media 50d relativa al universo",
    "rn_cs_rsi_rank":    "RSI cruzado vs el universo",
    "rn_sma20_slope":    "Tendencia de la media móvil (momentum)",
    "rn_mkt_ret10":      "Retorno del IPC últimos 10 días",
    "rn_wti_ret5":       "Precio del petróleo (WTI) últimos 5d",
}


def regime_label(naftrac_df: pd.DataFrame) -> dict:
    """Detecta el régimen actual del mercado con la MA del NAFTRAC."""
    if naftrac_df is None or len(naftrac_df) < 50:
        return {"estado": "desconocido", "emoji": "⚪", "descripcion": "Sin datos del índice"}
    c = naftrac_df["Close"]
    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    ultimo = c.iloc[-1]
    m20 = ma20.iloc[-1]
    m50 = ma50.iloc[-1]
    ret10 = (ultimo / c.iloc[-11] - 1) * 100 if len(c) > 11 else 0
    if ultimo > m20 > m50 and ret10 > 0:
        return {"estado": "alcista", "emoji": "🟢",
                "descripcion": f"IPC sobre MA20 y MA50, sube {ret10:+.1f}% en 10 días — buen momento para estar invertido"}
    elif ultimo < m20 and ret10 < -3:
        return {"estado": "bajista", "emoji": "🔴",
                "descripcion": f"IPC bajo MA20, cae {ret10:+.1f}% en 10 días — considera reducir exposición"}
    else:
        return {"estado": "lateral", "emoji": "🟡",
                "descripcion": f"IPC sin tendencia clara ({ret10:+.1f}% en 10d) — mantener posiciones con precaución"}


def explain_ticker(ticker: str, row: pd.Series, feat_importance: pd.Series) -> list[str]:
    """Las 3 razones principales por las que el modelo puso este ticker en el top."""
    reasons = []
    top_feats = feat_importance.head(20).index.tolist()
    for feat in top_feats:
        if feat not in row.index or pd.isna(row[feat]):
            continue
        val = row[feat]
        label = FEAT_LABELS.get(feat, feat.replace("rn_", "").replace("_", " "))
        if val > 0.70:
            reasons.append(f"✅ {label} — top {100-int(val*100)}% del universo")
        elif val < 0.30:
            reasons.append(f"⚠️ {label} — bottom {int(val*100)}% del universo")
        if len(reasons) >= 3:
            break
    return reasons if reasons else ["ℹ️ Combinación de factores técnicos favorables"]


def next_rebalance() -> str:
    """Próxima fecha de rebalanceo: ~20 días hábiles desde hoy."""
    d = date.today()
    bdays = 0
    while bdays < 20:
        d += timedelta(days=1)
        if d.weekday() < 5:
            bdays += 1
    return d.strftime("%d %b %Y")


def main(capital: float = 50_000.0):
    print("\n" + "═" * 60)
    print("  SEÑAL MENSUAL BMV  |  " + date.today().strftime("%B %Y").upper())
    print("═" * 60)

    # ── Cargar y preparar datos ──────────────────────────────────────────────
    print("\n[1/3] Preparando datos del mercado...")
    df = build_cross_sectional(HORIZON).sort_index()
    df = add_rank_normalized(df)

    # ── Entrenar con TODO el histórico disponible ────────────────────────────
    print("[2/3] Entrenando modelo con todo el historial disponible...")
    reg = lgb.LGBMRegressor(**_LGBM_BASE)
    reg.fit(df[RN_COLS].values, df["pct_fwd"].values)
    feat_imp = pd.Series(reg.feature_importances_, index=RN_COLS).sort_values(ascending=False)

    # ── Predecir sobre los datos MÁS RECIENTES de cada ticker ───────────────
    print("[3/3] Calculando ranking actual...")
    latest_rows = []
    macro = {n: store_get(n) for n in MACRO_TICKERS}
    macro = {k: v for k, v in macro.items() if v is not None}
    naftrac = macro.get("NAFTRAC")

    feat_frames = {}
    for ticker in BMV_TICKERS:
        raw = store_get(ticker)
        if raw is None or len(raw) < 100:
            continue
        try:
            feat = compute_features(raw)
            feat = add_macro_features(feat, macro)
            feat["ticker"] = ticker
            feat_frames[ticker] = feat
        except Exception:
            continue

    feat_frames = add_cross_section_features(feat_frames)

    for ticker, feat in feat_frames.items():
        df_t = feat.dropna(subset=FEATURE_COLS)
        if df_t.empty:
            continue
        last = df_t.iloc[-1].copy()
        # Rank-normalizar usando el universo del día más reciente
        for c in FEATURE_COLS:
            vals = [f.iloc[-1][c] for f in feat_frames.values()
                    if c in f.columns and not pd.isna(f.iloc[-1][c])]
            if vals:
                rk = sum(1 for v in vals if v <= last[c]) / len(vals)
                last[f"rn_{c}"] = rk
            else:
                last[f"rn_{c}"] = 0.5
        last["ticker"] = ticker
        latest_rows.append(last)

    if not latest_rows:
        print("ERROR: sin datos suficientes"); sys.exit(1)

    today_df = pd.DataFrame(latest_rows)
    rn_available = [c for c in RN_COLS if c in today_df.columns]
    today_df["score"] = reg.predict(today_df[rn_available].fillna(0.5).values)
    today_df = today_df.sort_values("score", ascending=False).reset_index(drop=True)

    # ── Régimen de mercado ────────────────────────────────────────────────────
    regime = regime_label(naftrac)

    # ── Construir output ──────────────────────────────────────────────────────
    top5 = today_df.head(TOP_N)
    bottom5 = today_df.tail(TOP_N)
    monto_por_nombre = capital / TOP_N

    picks = []
    for _, row in top5.iterrows():
        ticker = row["ticker"]
        raw = store_get(ticker)
        precio = float(raw["Close"].iloc[-1]) if raw is not None and len(raw) > 0 else None
        acciones = int(monto_por_nombre / precio) if precio and precio > 0 else None
        razones = explain_ticker(ticker, row, feat_imp)
        picks.append({
            "ticker": ticker,
            "score": round(float(row["score"]), 3),
            "score_pct": f"{int(row['score'] * 100)}%",
            "precio_actual": round(precio, 2) if precio else None,
            "monto_mxn": round(monto_por_nombre, 2),
            "acciones_aprox": acciones,
            "razones": razones,
        })

    evitar = [row["ticker"] for _, row in bottom5.iterrows()]

    out = {
        "fecha_generacion": date.today().isoformat(),
        "proximo_rebalanceo": next_rebalance(),
        "capital_total": capital,
        "monto_por_nombre": round(monto_por_nombre, 2),
        "mercado": regime,
        "top5": picks,
        "evitar": evitar,
        "universo_completo": [
            {"ticker": row["ticker"], "score": round(float(row["score"]), 3),
             "rank": i + 1}
            for i, (_, row) in enumerate(today_df.iterrows())
        ],
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    # ── Imprimir resumen ──────────────────────────────────────────────────────
    print(f"\n  {regime['emoji']} RÉGIMEN: {regime['estado'].upper()}")
    print(f"  {regime['descripcion']}")
    print(f"\n  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  COMPRAR ESTE MES (${capital:,.0f} MXN → ${monto_por_nombre:,.0f} por nombre)  ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    for i, p in enumerate(picks):
        precio_str = f"${p['precio_actual']:,.2f}" if p["precio_actual"] else "N/A"
        acc_str    = f"~{p['acciones_aprox']} acciones" if p["acciones_aprox"] else ""
        print(f"  ║  {i+1}. {p['ticker']:10s}  score {p['score_pct']:>4}  {precio_str:>10}  {acc_str:<18}  ║")
        for r in p["razones"]:
            print(f"  ║     {r:<54}  ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    print(f"  ║  EVITAR: {', '.join(evitar):<48}  ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    print(f"  ║  ⏰ Próximo rebalanceo: {next_rebalance():<34}  ║")
    print(f"  ╚══════════════════════════════════════════════════════════╝")
    print(f"\n  Guardado en: {OUT_PATH}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=50_000.0)
    args = parser.parse_args()
    main(capital=args.capital)
