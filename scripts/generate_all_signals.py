"""
Motor de señal mensual multi-universo.

Genera el ranking top-N para CUALQUIER universo de GBM
(BMV, USA/SIC, ETFs, Cripto-proxy, FIBRAs) con el mismo
modelo cross-seccional v2a.

También integra sentimiento de noticias via Vertex AI (Gemini)
si GCP_PROJECT_ID está configurado en .env.

Uso:
    python scripts/generate_all_signals.py
    python scripts/generate_all_signals.py --capital 50000 --universe "ETFs"
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
import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.universes import UNIVERSES
from src.ml.features import (compute_features, add_macro_features,
                              add_cross_section_features, FEATURE_COLS,
                              TECH_FEATURE_COLS)
from scripts.cross_sectional_v2 import add_rank_normalized, RN_COLS, _LGBM_BASE

OUT_DIR = ROOT / "data" / "signals"
OUT_DIR.mkdir(exist_ok=True)

FEAT_LABELS = {
    "rn_cs_mom_rank":    "Momentum relativo al universo",
    "rn_ret_20d":        "Retorno último mes vs pares",
    "rn_ret_5d":         "Retorno última semana vs pares",
    "rn_vol_ratio_20":   "Volumen inusualmente alto",
    "rn_rsi_14":         "RSI relativo vs pares",
    "rn_price_vs_sma20": "Precio sobre media 20d vs pares",
    "rn_price_vs_sma50": "Precio sobre media 50d vs pares",
    "rn_sma20_slope":    "Tendencia alcista de la media",
    "rn_obv_slope":      "Flujo de dinero (OBV)",
    "rn_bb_pct":         "Posición en Bollinger vs pares",
    "rn_atr_pct":        "Volatilidad relativa",
    "rn_sp500_ret5":     "Impulso de Wall Street",
    "rn_mkt_ret10":      "Retorno del benchmark 10d",
    "rn_wti_ret5":       "Precio del petróleo (WTI)",
    "rn_usdmxn_ret5":    "Movimiento del peso",
}


# ── Descarga de activos macro ─────────────────────────────────────────────────

MACRO_SYMBOLS = {
    "USDMXN":  "MXN=X",
    "NAFTRAC": "NAFTRACISHRS.MX",
    "WTI":     "CL=F",
    "SP500":   "^GSPC",
}

def download_macro() -> dict[str, pd.DataFrame]:
    """Descarga los 4 activos macro necesarios para add_macro_features()."""
    out: dict[str, pd.DataFrame] = {}
    symbols = list(MACRO_SYMBOLS.values())
    try:
        raw = yf.download(symbols, period="2y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            for key, sym in MACRO_SYMBOLS.items():
                try:
                    df = raw.xs(sym, axis=1, level=1).dropna(how="all")
                    if not df.empty:
                        out[key] = df
                except Exception:
                    pass
        else:
            # Un solo símbolo descargado
            first_key = list(MACRO_SYMBOLS.keys())[0]
            if not raw.empty:
                out[first_key] = raw
    except Exception as e:
        print(f"  ! Error descargando macro: {e}")
    return out


# ── Descarga de precios via yfinance ─────────────────────────────────────────

def download_prices(tickers: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Descarga OHLCV de todos los tickers del universo."""
    out = {}
    symbols = list(tickers.values())
    try:
        raw = yf.download(symbols, period="5y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            for name, sym in tickers.items():
                try:
                    df = raw.xs(sym, axis=1, level=1).dropna(how="all")
                    if len(df) > 100:
                        out[name] = df
                except Exception:
                    pass
        else:
            name = list(tickers.keys())[0]
            if len(raw) > 100:
                out[name] = raw
    except Exception as e:
        print(f"  ! Error descargando batch: {e}")
    return out


# ── Sentimiento vía Gemini (mismo patrón que TrabajadoresDomesticos) ──────────

def score_sentiment_gemini(noticias: list[str], tickers: list[str]) -> dict[str, float]:
    """
    Llama a Gemini 2.5-flash con API key para obtener sentimiento por ticker.
    Usa el mismo patrón que TrabajadoresDomesticos: google.genai.Client(api_key=...).
    Retorna {} si GEMINI_API_KEY no está configurado.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not noticias:
        return {}
    try:
        from google import genai                       # type: ignore[import]
        from google.genai import types as genai_types  # type: ignore[import]

        client = genai.Client(api_key=api_key)

        noticias_txt = "\n".join(f"- {n}" for n in noticias[:20])
        tickers_txt  = ", ".join(tickers)
        prompt = f"""Analiza el sentimiento de estas noticias financieras para las empresas listadas.
Para cada empresa asigna un score de -1 (muy negativo) a +1 (muy positivo). Si no hay noticias relevantes usa 0.
Responde SOLO con JSON: {{"TICKER": score, ...}}

Empresas: {tickers_txt}

Noticias:
{noticias_txt}"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=256,
                temperature=0.2,
            ),
        )
        text = (response.text or "").strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        print(f"  ! Gemini sentimiento: {e}")
    return {}


# ── Régimen de mercado ────────────────────────────────────────────────────────

def market_regime(benchmark_sym: str) -> dict:
    try:
        df = yf.download(benchmark_sym, period="3mo", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        c = df["Close"].dropna()
        if len(c) < 30:
            raise ValueError("pocas barras")
        ma20 = c.rolling(20).mean()
        ma50 = c.rolling(50).mean()
        ultimo, m20, m50 = c.iloc[-1], ma20.iloc[-1], ma50.iloc[-1]
        ret10 = (ultimo / c.iloc[-11] - 1) * 100 if len(c) > 11 else 0
        if ultimo > m20 > m50 and ret10 > 0:
            return {"estado": "alcista", "emoji": "🟢",
                    "descripcion": f"Benchmark sobre MA20 y MA50 ({ret10:+.1f}% en 10d) — buen momento"}
        elif ultimo < ma20.iloc[-1] and ret10 < -3:
            return {"estado": "bajista", "emoji": "🔴",
                    "descripcion": f"Benchmark bajo MA20 ({ret10:+.1f}% en 10d) — precaución"}
        return {"estado": "lateral", "emoji": "🟡",
                "descripcion": f"Sin tendencia clara ({ret10:+.1f}% en 10d) — neutral"}
    except Exception:
        return {"estado": "desconocido", "emoji": "⚪", "descripcion": "Sin datos del benchmark"}


# ── Motor principal ───────────────────────────────────────────────────────────

def generate_universe_signal(
    universe_name: str,
    capital: float = 50_000.0,
    top_n: int = 5,
) -> dict:
    cfg = UNIVERSES[universe_name]
    tickers = cfg["tickers"]
    horizon = cfg["horizonte"]
    benchmark = cfg["macro_benchmark"]
    min_n = cfg["min_tickers"]

    print(f"\n  [{universe_name}]  descargando {len(tickers)} tickers...")
    prices = download_prices(tickers)
    if len(prices) < min_n:
        return {"error": f"Solo {len(prices)} tickers disponibles (mínimo {min_n})"}

    # datos macro (USD/MXN, NAFTRAC, WTI, SP500) — necesarios para FEATURE_COLS
    print(f"  [{universe_name}]  descargando macro (USDMXN, NAFTRAC, WTI, SP500)...")
    macro_data = download_macro()

    # features técnicas + macro
    feat_frames = {}
    for name, df in prices.items():
        try:
            feat = compute_features(df)
            if macro_data:
                feat = add_macro_features(feat, macro_data)
            feat["ticker"] = name
            feat_frames[name] = feat
        except Exception:
            continue

    if len(feat_frames) < min_n:
        return {"error": "Insuficientes features calculadas"}

    feat_frames = add_cross_section_features(feat_frames)

    # columnas de features disponibles en este run
    available_feat_cols = [c for c in FEATURE_COLS if c in next(iter(feat_frames.values())).columns]

    # dataset con target para entrenar
    rows = []
    for name, df in feat_frames.items():
        df = df.dropna(subset=available_feat_cols)
        if len(df) < 100:
            continue
        df["fwd_ret"] = df["Close"].pct_change(horizon).shift(-horizon) * 100
        df = df.dropna(subset=available_feat_cols + ["fwd_ret"])
        rows.append(df)

    if not rows:
        return {"error": "Sin datos suficientes para entrenar"}

    full = pd.concat(rows).sort_index()
    full = add_rank_normalized(full)
    full = full.dropna(subset=RN_COLS + ["pct_fwd"])

    # entrenar
    reg = lgb.LGBMRegressor(**_LGBM_BASE)
    reg.fit(full[RN_COLS].values, full["pct_fwd"].values)

    # predecir sobre los datos más recientes de cada ticker
    today_rows = []
    # recalcular ranks del universo de hoy
    last_vals = {}
    for name, df in feat_frames.items():
        df_clean = df.dropna(subset=available_feat_cols)
        if df_clean.empty:
            continue
        last_vals[name] = df_clean.iloc[-1]

    if not last_vals:
        return {"error": "Sin datos recientes"}

    for name, row in last_vals.items():
        rn_row = {}
        for c in available_feat_cols:
            vals = [r[c] for r in last_vals.values() if c in r.index and not pd.isna(r[c])]
            rn_row[f"rn_{c}"] = sum(1 for v in vals if v <= row.get(c, 0)) / len(vals) if vals else 0.5
        rn_row["ticker"] = name
        today_rows.append(rn_row)

    today_df = pd.DataFrame(today_rows)
    rn_cols_avail = [c for c in RN_COLS if c in today_df.columns]
    today_df["score"] = reg.predict(today_df[rn_cols_avail].fillna(0.5).values)
    today_df = today_df.sort_values("score", ascending=False).reset_index(drop=True)

    # precio actual de cada ticker
    def last_price(name: str) -> float | None:
        df = prices.get(name)
        if df is None or df.empty:
            return None
        return float(df["Close"].iloc[-1])

    # picks
    picks = []
    monto = capital / top_n
    for _, row in today_df.head(top_n).iterrows():
        name = row["ticker"]
        precio = last_price(name)
        acciones = int(monto / precio) if precio and precio > 0 else None
        # razones
        razones = []
        feat_imp = pd.Series(reg.feature_importances_, index=RN_COLS).sort_values(ascending=False)
        for feat in feat_imp.head(15).index:
            val = row.get(feat, 0.5)
            if pd.isna(val):
                continue
            label = FEAT_LABELS.get(feat, feat.replace("rn_", "").replace("_", " "))
            if val > 0.72:
                razones.append(f"✅ {label} — top {100-int(val*100)}% del universo")
            elif val < 0.28:
                razones.append(f"⚠️ {label} — bottom {int(val*100)}% del universo")
            if len(razones) >= 3:
                break
        picks.append({
            "ticker": name,
            "score": round(float(row["score"]), 3),
            "score_pct": f"{int(row['score']*100)}%",
            "precio_actual": round(precio, 2) if precio else None,
            "monto": round(monto, 2),
            "acciones_aprox": acciones,
            "razones": razones or ["ℹ️ Combinación de factores técnicos favorables"],
        })

    evitar = [row["ticker"] for _, row in today_df.tail(top_n).iterrows()]
    d_rebal = date.today()
    bdays = 0
    while bdays < horizon:
        d_rebal += timedelta(days=1)
        if d_rebal.weekday() < 5:
            bdays += 1

    return {
        "universe": universe_name,
        "descripcion": cfg["descripcion"],
        "moneda": cfg["moneda"],
        "fecha": date.today().isoformat(),
        "proximo_rebalanceo": d_rebal.strftime("%d %b %Y"),
        "capital": capital,
        "monto_por_nombre": round(monto, 2),
        "mercado": market_regime(benchmark),
        "top5": picks,
        "evitar": evitar,
        "universo_completo": [
            {"ticker": row["ticker"], "score": round(float(row["score"]), 3), "rank": i+1}
            for i, (_, row) in enumerate(today_df.iterrows())
        ],
        "n_tickers_analizados": len(today_df),
        "sentiment": {},  # se rellena si Gemini está configurado
    }


def main(capital: float = 50_000.0, target_universe: str | None = None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    universes = ([target_universe] if target_universe and target_universe in UNIVERSES
                 else list(UNIVERSES.keys()))

    all_results = {}
    for uname in universes:
        result = generate_universe_signal(uname, capital=capital)
        slug = UNIVERSES[uname]["slug"]
        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        all_results[uname] = result

        if "error" in result:
            print(f"  ✗ {uname}: {result['error']}")
            continue

        reg = result["mercado"]
        print(f"  {reg['emoji']} {uname} — {reg['estado'].upper()}")
        print(f"     Top: {' · '.join(p['ticker'] for p in result['top5'])}")
        print(f"     Rebalanceo: {result['proximo_rebalanceo']}")

    # Guardar índice consolidado
    idx_path = OUT_DIR / "index.json"
    idx_path.write_text(json.dumps({
        "fecha": date.today().isoformat(),
        "universos": list(all_results.keys()),
    }, ensure_ascii=False, indent=2))
    print(f"\n  Guardado en: {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=50_000.0)
    parser.add_argument("--universe", type=str, default=None)
    args = parser.parse_args()
    main(capital=args.capital, target_universe=args.universe)
