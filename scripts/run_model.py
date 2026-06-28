"""
Modelo WoE + Logistic Regression + LightGBM con Walk-Forward Validation.

Arquitectura:
  ├── Walk-forward: 252d train / 63d test, paso 21d
  ├── WoE re-computado en cada ventana de training (sin look-ahead)
  ├── Features: top-8 por IV (osciladores + momentum)
  ├── Modelo 1: Logistic Regression sobre WoE features
  ├── Modelo 2: LightGBM sobre features crudas
  └── Evaluación: AUC, calibración, simulación de estrategia

Ejecución:
    python scripts/run_model.py
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ml.features import compute_features, FEATURE_COLS
from src.ml.woe import compute_all_woe, woe_transform, iv_summary

# ─── Configuración ────────────────────────────────────────────────────────────

TICKERS: dict[str, str] = {
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

HORIZON      = 5      # días para el target
WARMUP       = 60     # días de calentamiento para features
TRAIN_DAYS   = 252    # días de entrenamiento por fold
TEST_DAYS    = 63     # días de test por fold
STEP_DAYS    = 21     # paso entre folds
PROB_THRESH  = 0.55   # umbral para señal de compra
N_BINS_WOE   = 8      # bins para WoE

# Top features seleccionados por IV del análisis WoE previo
TOP_FEATURES = [
    "williams_r", "stoch_k", "ret_10d", "bb_pct",
    "price_vs_sma20", "cci_20", "mfi_14", "rsi_14",
]


# ─── Descarga y construcción del dataset ─────────────────────────────────────

def build_dataset() -> pd.DataFrame:
    end   = datetime.today()
    start = (end - timedelta(days=int(2.5 * 365))).strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    rows: list[pd.DataFrame] = []
    for ticker, symbol in TICKERS.items():
        try:
            raw = yf.download(symbol, start=start, end=end_s,
                              auto_adjust=False, progress=False, actions=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            if len(raw) < WARMUP + HORIZON + 30:
                continue

            df = compute_features(raw)
            df.index = pd.to_datetime(df.index)

            entry  = raw["Open"].shift(-1)
            exit_  = raw["Close"].shift(-(HORIZON + 1))
            df["target_ret"] = (exit_ - entry) / (entry.abs() + 1e-8) * 100
            df["y"]          = (df["target_ret"] > 0).astype(int)
            df["ticker"]     = ticker
            df["date"]       = df.index

            df = df.dropna(subset=["y"] + TOP_FEATURES)
            df = df.iloc[WARMUP:]
            rows.append(df)
        except Exception:
            pass

    return pd.concat(rows, ignore_index=True).sort_values("date").reset_index(drop=True)


# ─── Walk-Forward ─────────────────────────────────────────────────────────────

def run_walk_forward(ds: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    dates = sorted(ds["date"].unique())
    if len(dates) < TRAIN_DAYS + TEST_DAYS:
        raise RuntimeError("Insuficientes fechas.")

    folds_meta: list[dict] = []
    all_preds:  list[dict] = []

    # Generar ventanas
    windows = []
    i = TRAIN_DAYS
    while i + TEST_DAYS <= len(dates):
        tr_start = dates[0]
        tr_end   = dates[i - 1]
        te_start = dates[i]
        te_end   = dates[min(i + TEST_DAYS - 1, len(dates) - 1)]
        windows.append((tr_start, tr_end, te_start, te_end))
        i += STEP_DAYS

    print(f"  Folds: {len(windows)}  |  Train: {TRAIN_DAYS}d  Test: {TEST_DAYS}d  Paso: {STEP_DAYS}d\n")

    for fold_idx, (tr_start, tr_end, te_start, te_end) in enumerate(windows):
        train = ds[(ds["date"] >= tr_start) & (ds["date"] <= tr_end)].copy()
        test  = ds[(ds["date"] >= te_start) & (ds["date"] <= te_end)].copy()

        if len(train) < 200 or len(test) < 30:
            continue

        # ── Paso 1: Calcular WoE en training ────────────────────────────────
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            woe_map = compute_all_woe(train, TOP_FEATURES, target_col="y", n_bins=N_BINS_WOE)

        # ── Paso 2: Transformar train y test a WoE ───────────────────────────
        train_w = woe_transform(train, woe_map)
        test_w  = woe_transform(test,  woe_map)

        woe_cols = [f"{f}_woe" for f in TOP_FEATURES if f"{f}_woe" in train_w.columns]
        if len(woe_cols) < 4:
            continue

        X_train_woe = train_w[woe_cols].fillna(0).values
        X_test_woe  = test_w[woe_cols].fillna(0).values
        X_train_raw = train[TOP_FEATURES].fillna(train[TOP_FEATURES].median()).values
        X_test_raw  = test[TOP_FEATURES].fillna(train[TOP_FEATURES].median()).values
        y_train     = train["y"].values
        y_test      = test["y"].values

        # ── Paso 3: Logistic Regression ───────────────────────────────────────
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train_woe)
        X_test_scaled  = scaler.transform(X_test_woe)

        lr = LogisticRegression(C=0.1, max_iter=500, random_state=42)
        lr.fit(X_train_scaled, y_train)
        p_lr = lr.predict_proba(X_test_scaled)[:, 1]

        # ── Paso 4: LightGBM ────────────────────────────────────────────────
        lgbm_params = {
            "objective":      "binary",
            "metric":         "auc",
            "n_estimators":   200,
            "learning_rate":  0.05,
            "num_leaves":     15,
            "min_child_samples": 30,
            "subsample":      0.8,
            "colsample_bytree": 0.8,
            "reg_alpha":      0.1,
            "reg_lambda":     1.0,
            "random_state":   42,
            "verbose":        -1,
        }
        lgbm_model = lgb.LGBMClassifier(**lgbm_params)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lgbm_model.fit(X_train_raw, y_train,
                           eval_set=[(X_test_raw, y_test)],
                           callbacks=[lgb.early_stopping(20, verbose=False),
                                      lgb.log_evaluation(-1)])
        p_lgbm = lgbm_model.predict_proba(X_test_raw)[:, 1]

        # ── Métricas ─────────────────────────────────────────────────────────
        try:
            auc_lr   = float(roc_auc_score(y_test, p_lr))
            auc_lgbm = float(roc_auc_score(y_test, p_lgbm))
            brier_lr   = float(brier_score_loss(y_test, p_lr))
            brier_lgbm = float(brier_score_loss(y_test, p_lgbm))
        except Exception:
            continue

        event_rate = float(y_test.mean())

        fold_meta = {
            "fold":        fold_idx,
            "train_start": str(tr_start)[:10],
            "train_end":   str(tr_end)[:10],
            "test_start":  str(te_start)[:10],
            "test_end":    str(te_end)[:10],
            "n_train":     int(len(train)),
            "n_test":      int(len(test)),
            "event_rate":  round(event_rate, 4),
            "auc_lr":      round(auc_lr, 4),
            "auc_lgbm":    round(auc_lgbm, 4),
            "brier_lr":    round(brier_lr, 4),
            "brier_lgbm":  round(brier_lgbm, 4),
        }
        folds_meta.append(fold_meta)

        # ── Guardar predicciones ─────────────────────────────────────────────
        for j in range(len(test)):
            all_preds.append({
                "fold":       fold_idx,
                "date":       str(test["date"].iloc[j])[:10],
                "ticker":     str(test["ticker"].iloc[j]),
                "y":          int(y_test[j]),
                "target_ret": round(float(test["target_ret"].iloc[j]), 4),
                "p_lr":       round(float(p_lr[j]), 4),
                "p_lgbm":     round(float(p_lgbm[j]), 4),
            })

        print(f"  Fold {fold_idx:2d} | {str(te_start)[:10]} → {str(te_end)[:10]} | "
              f"AUC LR={auc_lr:.3f}  LGBM={auc_lgbm:.3f} | "
              f"n_test={len(test)}")

    return folds_meta, pd.DataFrame(all_preds)


# ─── Evaluación de estrategia ─────────────────────────────────────────────────

def evaluate_strategy(preds: pd.DataFrame) -> dict:
    """Simula operar cuando P(subida) > threshold."""
    out: dict = {}

    for model, col in [("logistic", "p_lr"), ("lgbm", "p_lgbm")]:
        signals = preds[preds[col] > PROB_THRESH].copy()
        if len(signals) == 0:
            continue

        win_rate  = float(signals["y"].mean())
        mean_ret  = float(signals["target_ret"].mean())
        std_ret   = float(signals["target_ret"].std())
        n_signals = int(len(signals))
        sharpe    = float(mean_ret / (std_ret + 1e-8) * np.sqrt(252 / HORIZON))

        # Calibración por buckets de probabilidad
        buckets = []
        edges = np.arange(0.40, 0.80, 0.05)
        for lo, hi in zip(edges, edges[1:]):
            sub = preds[(preds[col] >= lo) & (preds[col] < hi)]
            if len(sub) >= 10:
                buckets.append({
                    "bucket":       f"{lo:.2f}–{hi:.2f}",
                    "mean_pred":    round(float(sub[col].mean()), 4),
                    "actual_rate":  round(float(sub["y"].mean()), 4),
                    "n":            int(len(sub)),
                })

        # Distribución de retornos
        percentiles = {}
        for p in [5, 25, 50, 75, 95]:
            percentiles[f"p{p}"] = round(float(np.percentile(signals["target_ret"], p)), 3)

        out[model] = {
            "threshold":  PROB_THRESH,
            "n_signals":  n_signals,
            "n_total":    int(len(preds)),
            "signal_pct": round(n_signals / len(preds) * 100, 1),
            "win_rate":   round(win_rate, 4),
            "mean_ret":   round(mean_ret, 4),
            "std_ret":    round(std_ret, 4),
            "sharpe":     round(sharpe, 3),
            "calibration": buckets,
            "percentiles": percentiles,
        }

        print(f"\n  {model.upper()} (P > {PROB_THRESH}):")
        print(f"    Señales:   {n_signals:,} / {len(preds):,} ({n_signals/len(preds)*100:.1f}%)")
        print(f"    Win rate:  {win_rate:.1%}")
        print(f"    Media ret: {mean_ret:+.2f}%")
        print(f"    Sharpe:    {sharpe:.2f}")

    return out


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*64}")
    print(f"  MODELO WoE + LOGISTIC + LightGBM  |  Walk-Forward Validation")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  BMV 19 tickers")
    print(f"{'='*64}\n")

    print("1. Construyendo dataset...")
    ds = build_dataset()
    print(f"   {len(ds):,} observaciones · {ds['ticker'].nunique()} tickers · "
          f"{ds['date'].nunique()} fechas\n")

    print("2. Walk-Forward Validation...\n")
    folds_meta, preds = run_walk_forward(ds)

    if len(folds_meta) == 0:
        print("ERROR: No se generaron folds válidos")
        return

    # Métricas globales
    df_folds = pd.DataFrame(folds_meta)
    agg = {
        "n_folds":        int(len(df_folds)),
        "mean_auc_lr":    round(float(df_folds["auc_lr"].mean()), 4),
        "std_auc_lr":     round(float(df_folds["auc_lr"].std()),  4),
        "mean_auc_lgbm":  round(float(df_folds["auc_lgbm"].mean()), 4),
        "std_auc_lgbm":   round(float(df_folds["auc_lgbm"].std()),  4),
        "mean_brier_lr":  round(float(df_folds["brier_lr"].mean()), 4),
        "mean_brier_lgbm":round(float(df_folds["brier_lgbm"].mean()), 4),
        "mean_event_rate":round(float(df_folds["event_rate"].mean()), 4),
    }
    print(f"\n  AUC LR:    {agg['mean_auc_lr']:.4f} ± {agg['std_auc_lr']:.4f}")
    print(f"  AUC LGBM:  {agg['mean_auc_lgbm']:.4f} ± {agg['std_auc_lgbm']:.4f}")
    print(f"  Brier LR:  {agg['mean_brier_lr']:.4f}")
    print(f"  Brier LGBM:{agg['mean_brier_lgbm']:.4f}")

    print("\n3. Evaluando estrategia...")
    strategy = evaluate_strategy(preds)

    # Guardar
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    results = {
        "meta": {
            "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
            "n_obs":        int(len(ds)),
            "n_tickers":    int(ds["ticker"].nunique()),
            "train_days":   TRAIN_DAYS,
            "test_days":    TEST_DAYS,
            "step_days":    STEP_DAYS,
            "horizon":      HORIZON,
            "features":     TOP_FEATURES,
        },
        "aggregate": agg,
        "folds": folds_meta,
        "strategy": strategy,
        "predictions_sample": preds.head(500).to_dict(orient="records"),
    }

    (data_dir / "model_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    preds.to_csv(data_dir / "model_predictions.csv", index=False)

    print(f"\n  Guardado: data/model_results.json")
    print(f"           data/model_predictions.csv  ({len(preds):,} predicciones)\n")


if __name__ == "__main__":
    main()
