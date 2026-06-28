"""
Backtester BMV — validación histórica de señales técnicas
=========================================================
Simula el screener en datos históricos sin look-ahead bias.

Entrada:  OHLCV histórico de 19 tickers del IPC + NAFTRAC (benchmark)
Salida:   data/backtest_trades.csv  — cada trade simulado
          data/backtest_results.json — resumen estadístico por señal/horizonte

Ejecución:
    python scripts/run_backtest.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Añadir raíz del proyecto al path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ml.features import (
    compute_features,
    compute_target,
    compute_signal_score,
    score_to_category,
    FEATURE_COLS,
)

# ─── Universo ─────────────────────────────────────────────────────────────────
TICKERS: dict[str, str] = {
    "WALMEX":   "WALMEX.MX",
    "FEMSAUBD": "FEMSAUBD.MX",
    "GMEXICOB": "GMEXICOB.MX",
    "CEMEXCPO": "CEMEXCPO.MX",
    "GFNORTEO": "GFNORTEO.MX",
    "BIMBOA":   "BIMBOA.MX",
    "ALSEA":    "ALSEA.MX",
    "KIMBERA":  "KIMBERA.MX",
    "PINFRA":   "PINFRA.MX",
    "ORBIA":    "ORBIA.MX",
    "GRUMAB":   "GRUMAB.MX",
    "ASURB":    "ASURB.MX",
    "OMAB":     "OMAB.MX",
    "GAPB":     "GAPB.MX",
    "GCARSOA1": "GCARSOA1.MX",
    "MEGACPO":  "MEGACPO.MX",
    "LABB":     "LABB.MX",
    "Q":        "Q.MX",
    "VOLARA":   "VOLARA.MX",
}

BENCHMARK = "NAFTRAC.MX"
HOLDING_PERIODS = [3, 5, 10, 15, 20]
WARMUP_DAYS = 60     # días mínimos para calcular indicadores


# ─── Descarga ─────────────────────────────────────────────────────────────────

def download(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end,
                     auto_adjust=False, progress=False, actions=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# ─── Backtest por ticker ──────────────────────────────────────────────────────

def backtest_ticker(
    ticker: str,
    df: pd.DataFrame,
    bench_close: pd.Series,
) -> list[dict]:
    """Simula todos los días de señal para un ticker."""
    if len(df) < WARMUP_DAYS + max(HOLDING_PERIODS) + 2:
        return []

    df = compute_features(df)

    trades: list[dict] = []
    n = len(df)

    for i in range(WARMUP_DAYS, n - max(HOLDING_PERIODS) - 2):
        row = df.iloc[i]

        # Requiere todos los features clave
        if row[["rsi_14", "price_vs_sma20", "sma20_vs_sma50", "ret_5d"]].isna().any():
            continue

        score, signals = compute_signal_score(row)
        category = score_to_category(score)

        # Entrada: Open del día siguiente
        entry_price = float(df["Open"].iloc[i + 1])
        if entry_price <= 0 or np.isnan(entry_price):
            continue

        # Stop loss: 2 × ATR(14) debajo del precio de entrada
        atr = float(row.get("_atr14", 0) or 0)
        stop_price = entry_price - 2 * atr

        # Benchmark en la fecha de entrada
        entry_date = df.index[i + 1]

        for hp in HOLDING_PERIODS:
            exit_idx = i + 1 + hp
            if exit_idx >= n:
                continue

            # Verificar si el stop fue tocado en algún día del holding period
            stop_hit   = False
            stop_ret   = 0.0
            exit_price = float(df["Close"].iloc[exit_idx])

            for j in range(i + 1, exit_idx + 1):
                if float(df["Low"].iloc[j]) <= stop_price:
                    stop_hit   = True
                    exit_price = stop_price
                    break

            ret = (exit_price - entry_price) / entry_price * 100

            # Alpha vs benchmark (mismo período)
            bench_ret = np.nan
            exit_date = df.index[exit_idx]
            if entry_date in bench_close.index:
                b_entry = float(bench_close.loc[entry_date])
                later = bench_close.index[bench_close.index >= exit_date]
                if len(later):
                    bench_ret = (float(bench_close.loc[later[0]]) - b_entry) / b_entry * 100

            trades.append({
                "ticker":         ticker,
                "signal_date":    df.index[i].strftime("%Y-%m-%d"),
                "entry_date":     entry_date.strftime("%Y-%m-%d"),
                "score":          round(score, 1),
                "category":       category,
                "holding_period": hp,
                "entry_price":    round(entry_price, 4),
                "exit_price":     round(exit_price, 4),
                "return_pct":     round(ret, 4),
                "bench_ret":      round(bench_ret, 4) if pd.notna(bench_ret) else None,
                "alpha":          round(ret - bench_ret, 4) if pd.notna(bench_ret) else None,
                "stop_hit":       stop_hit,
                # features clave para WoE posterior
                "rsi_14":         round(float(row["rsi_14"]), 1),
                "pos_52w":        round(float(row["pos_52w"]), 1) if pd.notna(row.get("pos_52w")) else None,
                "price_vs_sma20": round(float(row["price_vs_sma20"]), 2),
                "sma20_vs_sma50": round(float(row["sma20_vs_sma50"]), 2),
                "ret_5d":         round(float(row["ret_5d"]), 2),
                "vol_ratio_20":   round(float(row.get("vol_ratio_20", np.nan)), 2) if pd.notna(row.get("vol_ratio_20")) else None,
                "bb_pos":         round(float(row.get("bb_pos", np.nan)), 1) if pd.notna(row.get("bb_pos")) else None,
                "signals":        "|".join(signals),
            })

    return trades


# ─── Estadísticas de resumen ──────────────────────────────────────────────────

def stats(returns: pd.Series, risk_free_daily: float = 0.10 / 252) -> dict:
    """Métricas clave para un conjunto de retornos (en %)."""
    r = returns.dropna()
    if len(r) < 5:
        return {}
    wins = (r > 0).sum()
    losses = (r < 0).sum()
    profit_factor = (
        r[r > 0].sum() / (-r[r < 0].sum() + 1e-8)
        if losses > 0 else float("inf")
    )
    # Sharpe simplificado (retornos % diarios sobre el holding period)
    excess = r - risk_free_daily * 252  # annualized benchmark
    return {
        "n":             int(len(r)),
        "win_rate":      round(float(wins / len(r) * 100), 1),
        "avg_ret":       round(float(r.mean()), 3),
        "median_ret":    round(float(r.median()), 3),
        "std":           round(float(r.std()), 3),
        "sharpe":        round(float(r.mean() / (r.std() + 1e-8)), 3),
        "avg_alpha":     None,   # se rellena después
        "profit_factor": round(float(profit_factor), 2),
        "stop_hit_rate": None,   # se rellena después
        "best":          round(float(r.max()), 2),
        "worst":         round(float(r.min()), 2),
        "pct_above_2":   round(float((r > 2).mean() * 100), 1),
        "pct_below_m2":  round(float((r < -2).mean() * 100), 1),
    }


def analyze(df: pd.DataFrame) -> dict:
    """Resumen completo por señal y horizonte."""
    out: dict = {}

    for hp in HOLDING_PERIODS:
        sub = df[df["holding_period"] == hp].copy()
        by_cat: dict = {}

        for cat in ["COMPRA", "VIGILAR", "NEUTRO", "EVITAR"]:
            t = sub[sub["category"] == cat]
            if len(t) < 10:
                continue
            s = stats(t["return_pct"])
            if not s:
                continue
            s["avg_alpha"]     = round(float(t["alpha"].dropna().mean()), 3) if t["alpha"].notna().any() else None
            s["stop_hit_rate"] = round(float(t["stop_hit"].mean() * 100), 1)
            by_cat[cat] = s

        # Análisis por feature individual (para WoE preview)
        feature_corrs: dict = {}
        for feat in ["rsi_14", "pos_52w", "price_vs_sma20", "ret_5d", "vol_ratio_20", "bb_pos"]:
            col = sub[feat].dropna()
            target = sub.loc[col.index, "return_pct"]
            if len(col) > 30:
                corr = float(col.corr(target))
                feature_corrs[feat] = round(corr, 3)

        out[f"hp_{hp}d"] = {"by_category": by_cat, "feature_corr_vs_return": feature_corrs}

    return out


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    years = 2.5
    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=int(years * 365))
    start    = start_dt.strftime("%Y-%m-%d")
    end      = end_dt.strftime("%Y-%m-%d")

    print(f"\n{'='*62}")
    print(f"  BACKTEST BMV  |  {start} → {end}")
    print(f"  {len(TICKERS)} tickers · horizonte {min(HOLDING_PERIODS)}-{max(HOLDING_PERIODS)}d")
    print(f"{'='*62}\n")

    # Benchmark
    print("  Descargando benchmark NAFTRAC...")
    bench_df = download(BENCHMARK, start, end)
    bench_close = bench_df["Close"].dropna() if not bench_df.empty else pd.Series(dtype=float)

    # Tickers
    all_trades: list[dict] = []
    for ticker, symbol in TICKERS.items():
        print(f"  {ticker:<12} ({symbol})...", end=" ", flush=True)
        raw = download(symbol, start, end)
        if raw.empty or len(raw) < WARMUP_DAYS:
            print("SKIP (sin datos)")
            continue
        trades = backtest_ticker(ticker, raw, bench_close)
        print(f"{len(trades)} trades")
        all_trades.extend(trades)

    if not all_trades:
        print("\n[ERROR] No se generaron trades.")
        return

    df = pd.DataFrame(all_trades)

    # ── Estadísticas ──────────────────────────────────────────────────────────
    summary = analyze(df)
    meta = {
        "date_range":       f"{df['signal_date'].min()} → {df['signal_date'].max()}",
        "tickers":          int(df["ticker"].nunique()),
        "total_signals":    int(len(df) // len(HOLDING_PERIODS)),
        "total_trades":     int(len(df)),
        "category_counts":  df[df["holding_period"] == 5]["category"].value_counts().to_dict(),
    }

    # ── Print resumen ─────────────────────────────────────────────────────────
    print(f"\n{'─'*62}")
    print(f"  {meta['total_signals']:,} señales  ·  {meta['tickers']} tickers  ·  {meta['date_range']}")
    print(f"{'─'*62}")

    for hp in [5, 10]:
        key = f"hp_{hp}d"
        if key not in summary:
            continue
        print(f"\n  Holding {hp}d:")
        print(f"  {'Señal':<10} {'N':>5}  {'Win%':>6}  {'AvgRet':>8}  {'Alpha':>8}  {'Sharpe':>7}  {'PF':>5}")
        print(f"  {'─'*55}")
        for cat in ["COMPRA", "VIGILAR", "NEUTRO", "EVITAR"]:
            s = summary[key]["by_category"].get(cat)
            if not s:
                continue
            alpha = f"{s['avg_alpha']:+.3f}%" if s["avg_alpha"] is not None else "   —  "
            print(
                f"  {cat:<10} {s['n']:>5}  {s['win_rate']:>5.1f}%  "
                f"{s['avg_ret']:>+7.3f}%  {alpha}  "
                f"{s['sharpe']:>7.3f}  {s['profit_factor']:>5.2f}"
            )

    print(f"\n  Correlaciones de features vs retorno a 5d:")
    corrs = summary.get("hp_5d", {}).get("feature_corr_vs_return", {})
    for feat, corr in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
        bar = "█" * int(abs(corr) * 20)
        sign = "+" if corr > 0 else "-"
        print(f"  {feat:<20} {sign}{bar:<20} {corr:+.3f}")

    # ── Guardar ───────────────────────────────────────────────────────────────
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    out = {"meta": meta, "summary": summary}
    (data_dir / "backtest_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )
    df.to_csv(data_dir / "backtest_trades.csv", index=False)

    print(f"\n  Guardado:")
    print(f"    data/backtest_results.json")
    print(f"    data/backtest_trades.csv  ({len(df):,} rows)\n")


if __name__ == "__main__":
    main()
