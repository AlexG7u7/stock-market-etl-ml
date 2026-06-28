"""
Evaluación hold-out temporal: entrena WoE + LR en el 80% inicial de la serie
y evalúa en el 20% más reciente (los últimos ~14 meses).

Diferencia con walk-forward:
  - Walk-forward: 6 ventanas móviles → mide estabilidad en el tiempo
  - Hold-out 20%: 1 corte temporal → mide rendimiento en datos recientes con
    todo el historial disponible para entrenar

Por qué es útil:
  - WoE entrenado con más datos = bins más estables
  - El test set ES el mercado actual → más relevante para trading en vivo
  - Complementa al walk-forward (no lo reemplaza)

Salida:
  data/holdout_results.json   — métricas, calibración, estrategia
  data/holdout_predictions.csv — predicciones out-of-sample del 20%
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store import get as store_get, BMV_TICKERS, MACRO_TICKERS
from src.ml.features import compute_features, add_macro_features, TECH_FEATURE_COLS, MACRO_FEATURE_COLS
from src.ml.woe import compute_all_woe, woe_transform, iv_summary

HORIZON      = 5
TARGET_RET   = 0.02      # y=1 si sube >2% en 5 días
PROB_THRESH  = 0.53
TRAIN_RATIO  = 0.80      # 80% train, 20% test
TOP_FEATURES = 12        # features WoE a usar
FEATURE_COLS = TECH_FEATURE_COLS + MACRO_FEATURE_COLS

print("=" * 65)
print("  Evaluación hold-out temporal 80/20")
print(f"  Train: primero {TRAIN_RATIO:.0%} de la serie")
print(f"  Test:  último {1-TRAIN_RATIO:.0%} (datos más recientes)")
print("=" * 65)

# ─── 1. Construir dataset completo ────────────────────────────────────────────
print("\n[1] Cargando datos y calculando features...")

macro: dict[str, pd.DataFrame] = {}
for name in MACRO_TICKERS:
    df = store_get(name)
    if df is not None:
        macro[name] = df.copy()

rows = []
for name in BMV_TICKERS:
    df = store_get(name)
    if df is None or len(df) < 100:
        continue
    feat = compute_features(df)
    feat = add_macro_features(feat, macro)
    feat["ticker"] = name
    feat["y"]      = (df["Close"].shift(-HORIZON) / df["Close"] - 1 >= TARGET_RET).astype(int)
    feat["ret_fwd"] = (df["Close"].shift(-HORIZON) / df["Close"] - 1) * 100
    rows.append(feat)

all_df = pd.concat(rows).sort_index()
all_df = all_df.dropna(subset=FEATURE_COLS + ["y"])

n_obs     = len(all_df)
date_min  = all_df.index.min()
date_max  = all_df.index.max()
base_rate = all_df["y"].mean()
print(f"   {n_obs:,} observaciones  |  {date_min.date()} → {date_max.date()}")
print(f"   Base rate global: {base_rate:.1%} suben >2% en {HORIZON}d")

# ─── 2. Corte temporal 80/20 ─────────────────────────────────────────────────
print("\n[2] Calculando corte temporal 80/20...")

# El corte se hace por FECHA, no por fila (evita data leakage entre tickers)
unique_dates  = all_df.index.unique().sort_values()
cutoff_idx    = int(len(unique_dates) * TRAIN_RATIO)
cutoff_date   = unique_dates[cutoff_idx]

train_df = all_df[all_df.index <  cutoff_date].copy()
test_df  = all_df[all_df.index >= cutoff_date].copy()

n_train_dates = train_df.index.nunique()
n_test_dates  = test_df.index.nunique()

print(f"   Corte: {cutoff_date.date()}")
print(f"   Train: {len(train_df):,} obs  ({train_df.index.min().date()} → {train_df.index.max().date()})  {n_train_dates} fechas")
print(f"   Test:  {len(test_df):,} obs  ({test_df.index.min().date()} → {test_df.index.max().date()})  {n_test_dates} fechas")
print(f"   Base rate train: {train_df['y'].mean():.1%}  |  test: {test_df['y'].mean():.1%}")

# ─── 3. WoE sobre train únicamente ───────────────────────────────────────────
print("\n[3] Calculando WoE en set de entrenamiento...")

woe_maps = compute_all_woe(train_df, FEATURE_COLS, target_col="y")

# IV summary y selección de features
iv_df = iv_summary(woe_maps)
top_feats = iv_df.head(TOP_FEATURES)["feature"].tolist()
print(f"   {len(woe_maps)} features analizados  |  usando top {TOP_FEATURES} por IV")
print(f"\n   Top features por IV:")
for _, row in iv_df.head(TOP_FEATURES).iterrows():
    bar = "█" * int(row["iv"] * 500)
    print(f"     {row['feature']:<22} IV={row['iv']:.4f}  {bar}")

# ─── 4. Transformar ambos sets con los bins del train ─────────────────────────
print("\n[4] Transformando features con WoE...")

X_train_woe = woe_transform(train_df[FEATURE_COLS], woe_maps)[top_feats]
X_test_woe  = woe_transform(test_df[FEATURE_COLS],  woe_maps)[top_feats]
y_train = train_df["y"]
y_test  = test_df["y"]

# Eliminar filas con NaN en features
mask_train = X_train_woe.notna().all(axis=1)
mask_test  = X_test_woe.notna().all(axis=1)
X_train_woe = X_train_woe[mask_train];  y_train = y_train[mask_train]
X_test_woe  = X_test_woe[mask_test];   y_test  = y_test[mask_test]
test_df_clean = test_df[mask_test].copy()

print(f"   Train usable: {len(X_train_woe):,}  |  Test usable: {len(X_test_woe):,}")

# ─── 5. Entrenar modelo ───────────────────────────────────────────────────────
print("\n[5] Entrenando Logistic Regression...")

scaler      = StandardScaler()
X_train_sc  = scaler.fit_transform(X_train_woe)
X_test_sc   = scaler.transform(X_test_woe)

model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
model.fit(X_train_sc, y_train)

# Coeficientes: qué tan importante es cada feature
coef_df = pd.DataFrame({
    "feature": top_feats,
    "coef":    model.coef_[0],
}).sort_values("coef", ascending=False)

print("\n   Coeficientes del modelo (+ = favorece subida):")
for _, row in coef_df.iterrows():
    direction = "↑" if row["coef"] > 0 else "↓"
    bar = "█" * int(abs(row["coef"]) * 8)
    print(f"     {direction} {row['feature']:<22} {row['coef']:>+.3f}  {bar}")

# ─── 6. Predicciones en test ──────────────────────────────────────────────────
print("\n[6] Generando predicciones en test set (20% final)...")

p_test = model.predict_proba(X_test_sc)[:, 1]
auc    = roc_auc_score(y_test, p_test)
brier  = brier_score_loss(y_test, p_test)

print(f"   AUC:          {auc:.4f}")
print(f"   Brier score:  {brier:.4f}  (menor = mejor calibración; 0.25 = azar)")

# ─── 7. Métricas de estrategia ────────────────────────────────────────────────
print(f"\n[7] Métricas de estrategia (umbral P ≥ {PROB_THRESH})...")

preds_df = test_df_clean.copy()
preds_df["p"]     = p_test
preds_df["signal"] = (preds_df["p"] >= PROB_THRESH).astype(int)

signals   = preds_df[preds_df["signal"] == 1]
n_signals = len(signals)
win_rate  = signals["y"].mean()          if n_signals else 0
mean_ret  = signals["ret_fwd"].mean()    if n_signals else 0
std_ret   = signals["ret_fwd"].std()     if n_signals else 1
sharpe    = mean_ret / (std_ret + 1e-8) * np.sqrt(252 / HORIZON)
pf_wins   = signals[signals["ret_fwd"] > 0]["ret_fwd"].sum()
pf_loss   = abs(signals[signals["ret_fwd"] < 0]["ret_fwd"].sum())
pf        = pf_wins / pf_loss if pf_loss > 0 else float("inf")

print(f"   Señales totales:  {n_signals} de {len(preds_df)} ({n_signals/len(preds_df)*100:.1f}%)")
print(f"   Win rate:         {win_rate:.1%}")
print(f"   Retorno medio:    {mean_ret:+.2f}%")
print(f"   Sharpe anual:     {sharpe:.2f}")
print(f"   Profit factor:    {pf:.2f}")

# Calibración por buckets
print(f"\n   Calibración (P predicha vs tasa real):")
buckets = []
edges = np.arange(0.40, 0.75, 0.05)
for lo, hi in zip(edges, edges[1:]):
    sub = preds_df[(preds_df["p"] >= lo) & (preds_df["p"] < hi)]
    if len(sub) < 5:
        continue
    actual_rate = sub["y"].mean()
    mean_pred   = sub["p"].mean()
    n_sub       = len(sub)
    bar_pred    = "░" * int(mean_pred * 30)
    bar_real    = "█" * int(actual_rate * 30)
    print(f"     P {lo:.2f}–{hi:.2f}  n={n_sub:>4}  pred={mean_pred:.0%}  real={actual_rate:.0%}  {bar_real}")
    buckets.append({
        "bucket":      f"{lo:.2f}–{hi:.2f}",
        "n":           int(n_sub),
        "mean_pred":   round(float(mean_pred), 4),
        "actual_rate": round(float(actual_rate), 4),
    })

# Performance por ticker
print(f"\n   Rendimiento por ticker en el test set:")
ticker_stats = []
for ticker, grp in signals.groupby("ticker"):
    wr  = grp["y"].mean()
    ret = grp["ret_fwd"].mean()
    n   = len(grp)
    icon = "✅" if wr > 0.5 else "⚠️" if wr > 0.4 else "❌"
    print(f"     {icon} {ticker:<14}  n={n:>3}  win={wr:.0%}  ret_medio={ret:+.1f}%")
    ticker_stats.append({"ticker": ticker, "n": n, "win_rate": round(wr, 3), "mean_ret": round(ret, 2)})

# ─── 8. Guardar resultados ────────────────────────────────────────────────────
print("\n[8] Guardando resultados...")

results = {
    "meta": {
        "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
        "train_ratio":  TRAIN_RATIO,
        "cutoff_date":  str(cutoff_date.date()),
        "train_start":  str(train_df.index.min().date()),
        "train_end":    str(train_df.index.max().date()),
        "test_start":   str(test_df_clean.index.min().date()),
        "test_end":     str(test_df_clean.index.max().date()),
        "n_train":      len(X_train_woe),
        "n_test":       len(X_test_woe),
        "n_features":   TOP_FEATURES,
        "base_rate_train": round(float(y_train.mean()), 4),
        "base_rate_test":  round(float(y_test.mean()), 4),
    },
    "performance": {
        "auc":         round(float(auc), 4),
        "brier":       round(float(brier), 4),
        "n_signals":   int(n_signals),
        "signal_pct":  round(n_signals / len(preds_df) * 100, 1),
        "win_rate":    round(float(win_rate), 4),
        "mean_ret":    round(float(mean_ret), 3),
        "std_ret":     round(float(std_ret), 3),
        "sharpe":      round(float(sharpe), 3),
        "profit_factor": round(float(pf), 3),
    },
    "calibration":   buckets,
    "ticker_stats":  ticker_stats,
    "iv_summary":    iv_df.head(TOP_FEATURES)[["feature","iv"]].rename(
                         columns={"iv":"iv"}).to_dict("records"),
    "coefficients":  coef_df.to_dict("records"),
    "wf_comparison": {
        "note": "Walk-forward AUC promedio está en model_results.json para comparación",
        "holdout_auc": round(float(auc), 4),
    },
}

out_dir = ROOT / "data"
out_dir.mkdir(exist_ok=True)
(out_dir / "holdout_results.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False)
)

# Predicciones detalladas
preds_out = preds_df[["ticker","y","ret_fwd","p","signal"]].copy()
preds_out.index.name = "date"
preds_out.to_csv(out_dir / "holdout_predictions.csv")

print(f"   ✅ holdout_results.json")
print(f"   ✅ holdout_predictions.csv  ({len(preds_out):,} filas)")
print()
print("=" * 65)
print(f"  RESUMEN FINAL")
print(f"  AUC en test 20%:    {auc:.4f}")
print(f"  Win rate (P≥{PROB_THRESH}):  {win_rate:.1%}")
print(f"  Sharpe anual:       {sharpe:.2f}")
print(f"  Profit factor:      {pf:.2f}")
print(f"  Período test:       {str(test_df_clean.index.min().date())} → {str(test_df_clean.index.max().date())}")
print("=" * 65)
