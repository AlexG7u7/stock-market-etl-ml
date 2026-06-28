"""
Motor de señal multi-universo y multi-horizonte.

Genera rankings para 4 horizontes por universo:
  1 semana (5d) · 2 semanas (10d) · 3 semanas (15d) · 4 semanas (20d)

Comparte descarga de precios y cómputo de features entre horizontes.
Integra análisis Gemini por ticker en el top-5.

Uso:
    python scripts/generate_all_signals.py
    python scripts/generate_all_signals.py --capital 50000 --universe "📦 ETFs"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

import lightgbm as lgb
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.universes import UNIVERSES
from src.ml.features import (compute_features, add_macro_features,
                              add_cross_section_features, FEATURE_COLS)
from scripts.cross_sectional_v2 import add_rank_normalized, RN_COLS, _LGBM_BASE

OUT_DIR = ROOT / "data" / "signals"
OUT_DIR.mkdir(exist_ok=True)

# ── Horizontes disponibles ────────────────────────────────────────────────────

HORIZONS = [
    {"key": "1s", "label": "1 semana",   "semanas": 1, "d": 5},
    {"key": "2s", "label": "2 semanas",  "semanas": 2, "d": 10},
    {"key": "3s", "label": "3 semanas",  "semanas": 3, "d": 15},
    {"key": "4s", "label": "4 semanas",  "semanas": 4, "d": 20},
]

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
    out: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(list(MACRO_SYMBOLS.values()), period="2y",
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            for key, sym in MACRO_SYMBOLS.items():
                try:
                    df = raw.xs(sym, axis=1, level=1).dropna(how="all")
                    if not df.empty:
                        out[key] = df
                except Exception:
                    pass
    except Exception as e:
        print(f"  ! macro: {e}")
    return out


def download_prices(tickers: dict[str, str]) -> dict[str, pd.DataFrame]:
    out = {}
    try:
        raw = yf.download(list(tickers.values()), period="5y",
                          auto_adjust=True, progress=False)
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
        print(f"  ! precios: {e}")
    return out


def market_regime(benchmark_sym: str) -> dict:
    try:
        df = yf.download(benchmark_sym, period="3mo", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        c = df["Close"].dropna()
        if len(c) < 30:
            raise ValueError
        ma20 = c.rolling(20).mean()
        ma50 = c.rolling(50).mean()
        ret10 = (c.iloc[-1] / c.iloc[-11] - 1) * 100 if len(c) > 11 else 0
        if c.iloc[-1] > ma20.iloc[-1] > ma50.iloc[-1] and ret10 > 0:
            return {"estado": "alcista", "emoji": "🟢",
                    "descripcion": f"Benchmark sobre MA20 y MA50 ({ret10:+.1f}% en 10d)"}
        elif c.iloc[-1] < ma20.iloc[-1] and ret10 < -3:
            return {"estado": "bajista", "emoji": "🔴",
                    "descripcion": f"Benchmark bajo MA20 ({ret10:+.1f}% en 10d) — precaución"}
        return {"estado": "lateral", "emoji": "🟡",
                "descripcion": f"Sin tendencia clara ({ret10:+.1f}% en 10d)"}
    except Exception:
        return {"estado": "desconocido", "emoji": "⚪", "descripcion": "Sin datos"}


# ── Ranking para un horizonte dado ────────────────────────────────────────────

def _next_bday(horizon_d: int) -> str:
    d = date.today()
    bd = 0
    while bd < horizon_d:
        d += timedelta(days=1)
        if d.weekday() < 5:
            bd += 1
    return d.strftime("%d %b %Y")


def _last_price(name: str, prices: dict) -> float | None:
    df = prices.get(name)
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


def rank_at_horizon(
    feat_frames: dict[str, pd.DataFrame],
    last_vals: dict,
    available_feat_cols: list[str],
    prices: dict,
    horizon_d: int,
    capital: float,
    top_n: int,
) -> dict | None:
    """Entrena modelo para un horizonte y retorna picks + ranking."""
    rows = []
    for name, df in feat_frames.items():
        df = df.dropna(subset=available_feat_cols)
        if len(df) < 100:
            continue
        df = df.copy()
        df["fwd_ret"] = df["Close"].pct_change(horizon_d).shift(-horizon_d) * 100
        df = df.dropna(subset=available_feat_cols + ["fwd_ret"])
        rows.append(df)

    if not rows:
        return None

    h_full = pd.concat(rows).sort_index()
    h_full = add_rank_normalized(h_full)
    h_full = h_full.dropna(subset=RN_COLS + ["pct_fwd"])

    if len(h_full) < 50:
        return None

    reg = lgb.LGBMRegressor(**_LGBM_BASE, verbose=-1)
    reg.fit(h_full[RN_COLS].values, h_full["pct_fwd"].values)

    # Predecir hoy
    today_rows = []
    for name, row in last_vals.items():
        rn_row = {"ticker": name}
        for c in available_feat_cols:
            vals = [r[c] for r in last_vals.values()
                    if c in r.index and not pd.isna(r[c])]
            rn_row[f"rn_{c}"] = (sum(1 for v in vals if v <= row.get(c, 0)) / len(vals)
                                  if vals else 0.5)
        today_rows.append(rn_row)

    today_df = pd.DataFrame(today_rows)
    rn_cols_avail = [c for c in RN_COLS if c in today_df.columns]
    today_df["score"] = reg.predict(today_df[rn_cols_avail].fillna(0.5).values)
    today_df = today_df.sort_values("score", ascending=False).reset_index(drop=True)

    feat_imp = pd.Series(reg.feature_importances_, index=RN_COLS).sort_values(ascending=False)
    monto = capital / top_n

    picks = []
    for _, row in today_df.head(top_n).iterrows():
        name   = row["ticker"]
        precio = _last_price(name, prices)
        razones = []
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
            "ticker":         name,
            "score":          round(float(row["score"]), 3),
            "score_pct":      f"{int(row['score']*100)}%",
            "precio_actual":  round(precio, 2) if precio else None,
            "monto":          round(monto, 2),
            "acciones_aprox": int(monto / precio) if precio and precio > 0 else None,
            "razones":        razones or ["ℹ️ Combinación de factores técnicos favorables"],
        })

    return {
        "top5":             picks,
        "evitar":           [r["ticker"] for _, r in today_df.tail(top_n).iterrows()],
        "proximo_rebalanceo": _next_bday(horizon_d),
        "universo_completo": [
            {"ticker": r["ticker"], "score": round(float(r["score"]), 3), "rank": i+1}
            for i, (_, r) in enumerate(today_df.iterrows())
        ],
    }


# ── Motor principal multi-horizonte ──────────────────────────────────────────

def generate_universe_signal(
    universe_name: str,
    capital: float = 50_000.0,
    top_n: int = 5,
) -> dict:
    cfg     = UNIVERSES[universe_name]
    tickers = cfg["tickers"]
    min_n   = cfg["min_tickers"]

    print(f"\n  [{universe_name}]  precios + macro...")
    prices     = download_prices(tickers)
    if len(prices) < min_n:
        return {"error": f"Solo {len(prices)} tickers (mínimo {min_n})"}
    macro_data = download_macro()

    # Features técnicas + macro — se calculan UNA VEZ para todos los horizontes
    feat_frames: dict[str, pd.DataFrame] = {}
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
        return {"error": "Insuficientes features"}

    feat_frames = add_cross_section_features(feat_frames)
    available_feat_cols = [c for c in FEATURE_COLS
                           if c in next(iter(feat_frames.values())).columns]

    # Datos de hoy para predicción (compartidos entre horizontes)
    last_vals: dict = {}
    for name, df in feat_frames.items():
        clean = df.dropna(subset=available_feat_cols)
        if not clean.empty:
            last_vals[name] = clean.iloc[-1]

    if not last_vals:
        return {"error": "Sin datos recientes"}

    # ── Entrenar modelo por horizonte ─────────────────────────────────────────
    by_horizon: dict[str, dict] = {}
    for h in HORIZONS:
        print(f"  [{universe_name}]  horizonte {h['label']} ({h['d']}d)...")
        result = rank_at_horizon(
            feat_frames, last_vals, available_feat_cols, prices,
            h["d"], capital, top_n,
        )
        if result:
            by_horizon[h["key"]] = {
                "label":    h["label"],
                "semanas":  h["semanas"],
                "horizon_d": h["d"],
                **result,
            }

    if not by_horizon:
        return {"error": "No se pudo entrenar ningún horizonte"}

    # ── Consenso: tickers que aparecen en top-5 de múltiples horizontes ───────
    ticker_counts: dict[str, list[str]] = defaultdict(list)
    for hkey, hdata in by_horizon.items():
        for p in hdata.get("top5", []):
            ticker_counts[p["ticker"]].append(hkey)

    consensus = sorted(
        [{"ticker": t, "n_horizontes": len(hs), "horizontes": hs}
         for t, hs in ticker_counts.items()],
        key=lambda x: -x["n_horizontes"],
    )

    # ── Gemini: analiza top tickers del consenso (máx 7 para no gastar API) ───
    top_consensus_tickers = [c["ticker"] for c in consensus[:7]]
    # Usar el ranking de 4 semanas como representativo para Gemini
    ref_picks = by_horizon.get("4s", by_horizon[list(by_horizon.keys())[0]])["top5"]
    ref_picks_filtered = [p for p in ref_picks if p["ticker"] in top_consensus_tickers]
    ref_picks_filtered += [p for p in ref_picks if p["ticker"] not in top_consensus_tickers]
    ref_picks_filtered = ref_picks_filtered[:top_n]

    from src.api.gemini_analyst import analyze_batch
    gemini_analyses = analyze_batch(
        ref_picks_filtered, cfg["tickers"], universe_name, universe_slug=cfg["slug"]
    )

    # Enriquecer picks de TODOS los horizontes con análisis Gemini
    for hkey, hdata in by_horizon.items():
        for p in hdata["top5"]:
            name = p["ticker"]
            a    = gemini_analyses.get(name, {})
            p["gemini"]   = {
                "resumen":          a.get("resumen", ""),
                "accion":           a.get("accion", ""),
                "riesgo":           a.get("riesgo", ""),
                "catalizador":      a.get("catalizador", ""),
                "sentimiento_news": a.get("sentimiento_news", ""),
            }
            p["noticias"] = a.get("noticias", [])

    # El horizonte por defecto del universo como campo de compatibilidad
    default_key = next((h["key"] for h in HORIZONS if h["d"] == cfg.get("horizonte", 20)), "4s")
    default     = by_horizon.get(default_key, by_horizon[list(by_horizon.keys())[-1]])

    return {
        "universe":            universe_name,
        "descripcion":         cfg["descripcion"],
        "moneda":              cfg["moneda"],
        "fecha":               date.today().isoformat(),
        "capital":             capital,
        "monto_por_nombre":    round(capital / top_n, 2),
        "mercado":             market_regime(cfg["macro_benchmark"]),
        "n_tickers_analizados": len(last_vals),
        # Horizonte por defecto (compatibilidad con versiones anteriores del app)
        "top5":                default["top5"],
        "evitar":              default["evitar"],
        "proximo_rebalanceo":  default["proximo_rebalanceo"],
        "universo_completo":   default["universo_completo"],
        # Multi-horizonte
        "by_horizon":          by_horizon,
        "consensus":           consensus,
    }


def main(capital: float = 50_000.0, target_universe: str | None = None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    universes = ([target_universe] if target_universe and target_universe in UNIVERSES
                 else list(UNIVERSES.keys()))

    for uname in universes:
        result = generate_universe_signal(uname, capital=capital)
        slug   = UNIVERSES[uname]["slug"]
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        if "error" in result:
            print(f"  ✗ {uname}: {result['error']}")
        else:
            m = result["mercado"]
            cons_top = [c["ticker"] for c in result["consensus"] if c["n_horizontes"] >= 3]
            print(f"  {m['emoji']} {uname} — {m['estado'].upper()}")
            for h in HORIZONS:
                hd = result["by_horizon"].get(h["key"])
                if hd:
                    tickers_str = " · ".join(p["ticker"] for p in hd["top5"])
                    print(f"     {h['label']:12s} → {tickers_str}")
            if cons_top:
                print(f"     ⭐ Consenso (≥3 horizontes): {' · '.join(cons_top)}")

    (OUT_DIR / "index.json").write_text(json.dumps({
        "fecha": date.today().isoformat(),
        "universos": universes,
    }, ensure_ascii=False, indent=2))
    print(f"\n  Guardado en: {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital",   type=float, default=50_000.0)
    parser.add_argument("--universe",  type=str,   default=None)
    args = parser.parse_args()
    main(capital=args.capital, target_universe=args.universe)
