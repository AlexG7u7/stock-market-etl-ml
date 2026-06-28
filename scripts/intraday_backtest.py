"""
¿La microestructura intradía rompe el techo de AUC ~0.527?

A/B controlado sobre la ventana donde existe intradía (nov-2024 → hoy), con los
18 tickers líquidos descargados. Compara, sobre el MISMO dataset:

  BASE      : features diarias (técnicas + macro + cross-section)
  +INTRADÍA : BASE + 8 features de microestructura (5m agregadas a diario)
  SOLO-ID   : ¿las features intradía por sí solas tienen AUC > 0.5?

Sin look-ahead: las features intradía de t se conocen al cierre de t; la entrada
del modelo es Open[t+1].

Ejecución:
    python scripts/intraday_backtest.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.data.store         import get as store_get, MACRO_TICKERS
from src.ml.features        import (compute_features, add_macro_features,
                                    add_cross_section_features, FEATURE_COLS)
from src.ml.intraday_features import add_intraday_features, INTRADAY_COLS, INTRADAY_DIR
from src.ml.labeling        import triple_barrier_labels
from src.ml.ensemble        import EnsembleModel
from scripts.experiments    import train_eval, fmt
from scripts.run_meta       import HORIZON, MULT_TARGET, MULT_STOP

INTRA_START = "2024-11-22"


def intraday_tickers() -> list[str]:
    return sorted(p.stem for p in INTRADAY_DIR.glob("*.parquet"))


def build_dataset_intraday(horizon: int = HORIZON) -> pd.DataFrame:
    """Dataset diario de los tickers con intradía + microestructura, restringido a la ventana."""
    macro = {n: store_get(n) for n in MACRO_TICKERS}
    macro = {k: v for k, v in macro.items() if v is not None}

    tickers = intraday_tickers()
    feat_frames = {}
    for ticker in tickers:
        raw = store_get(ticker)
        if raw is None or len(raw) < 200:
            continue
        try:
            feat = compute_features(raw)
            feat = add_macro_features(feat, macro)
            feat = add_intraday_features(feat, ticker)

            # Targets directos de corto plazo (entrada Open[t+1]):
            o, c = raw["Open"], raw["Close"]
            feat["y_next"] = ((c.shift(-1) - o.shift(-1)) / o.shift(-1) > 0).astype(int)        # 1 día
            feat["y_2d"]   = ((c.shift(-2) - o.shift(-1)) / o.shift(-1) > 0).astype(int)        # 2 días
            feat["y_3d"]   = ((c.shift(-3) - o.shift(-1)) / o.shift(-1) > 0).astype(int)        # 3 días

            vol = (feat["atr_pct"] / 100.0) if "atr_pct" in feat.columns else \
                  raw["Close"].pct_change().rolling(14).std()
            tb = triple_barrier_labels(
                close=raw["Close"], high=raw["High"], low=raw["Low"],
                vol=vol, horizon=horizon,
                mult_target=MULT_TARGET, mult_stop=MULT_STOP,
            )
            feat["y"]       = tb["label"]
            feat["tb_ret"]  = tb["ret"]
            feat["tb_bars"] = tb["bars"]
            feat["touch"]   = tb["touch"]
            feat["ticker"]  = ticker
            feat_frames[ticker] = feat
        except Exception as e:
            print(f"  {ticker}: {e}")

    feat_frames = add_cross_section_features(feat_frames)
    df = pd.concat(feat_frames.values()).sort_index()
    df = df[df.index >= pd.Timestamp(INTRA_START)]
    return df


def standalone_auc(df: pd.DataFrame, cols: list[str], target: str = "y") -> float:
    """AUC de un EnsembleModel usando SOLO las columnas dadas (80/20 temporal)."""
    d = df.dropna(subset=cols + [target]).sort_index()
    cut = d.index[int(len(d) * 0.80)]
    tr, te = d[d.index < cut], d[d.index >= cut]
    m = EnsembleModel(top_features=min(len(cols), 8), calibrate=False)
    m.fit(tr, feature_cols=cols, target_col=target)
    p = m.predict_proba(te, cols)
    return roc_auc_score(te[target], p) if te[target].nunique() > 1 else 0.5


def main():
    print("\n" + "=" * 80)
    print("  ¿ROMPE LA MICROESTRUCTURA INTRADÍA EL TECHO?  |  ventana nov-2024 → hoy")
    print("=" * 80)

    print("\n[1] Construyendo dataset diario + microestructura (5m → diario)...")
    df = build_dataset_intraday(horizon=HORIZON)
    base = df.dropna(subset=FEATURE_COLS + ["y"])
    cov = df.dropna(subset=INTRADAY_COLS).shape[0] / max(len(df), 1)
    print(f"    {len(base):,} obs diarias  |  {len(intraday_tickers())} tickers  "
          f"|  cobertura intradía {cov*100:.0f}%")
    print(f"    Período: {base.index.min().date()} → {base.index.max().date()}")

    feats_id = FEATURE_COLS + INTRADAY_COLS
    df_id = df.dropna(subset=feats_id + ["y"])

    print("\n[2] AUC de features SOLO-INTRADÍA por horizonte (¿dónde vive la señal?):")
    for tgt, lbl in [("y_next", "1 día"), ("y_2d", "2 días"), ("y_3d", "3 días"), ("y", "5d (triple-barrier)")]:
        a_solo = standalone_auc(df, INTRADAY_COLS, target=tgt)
        # AUC de base diaria al mismo horizonte, para referencia del techo
        a_base = standalone_auc(df, FEATURE_COLS, target=tgt)
        flag = ">0.51 ¡señal!" if a_solo > 0.51 else "≈0.5 sin señal"
        print(f"    {lbl:<22}  solo-ID={a_solo:.4f} ({flag})   base-diaria={a_base:.4f}")

    print("\n[3] BASE (diarias) vs +INTRADÍA — stack completo (Ensemble+Meta+Régimen):")
    r_base = train_eval(base,  FEATURE_COLS, horizon=HORIZON)
    r_id   = train_eval(df_id, feats_id,     horizon=HORIZON)
    print(f"    BASE      : {fmt(r_base)}")
    print(f"    +INTRADÍA : {fmt(r_id)}")

    print("\n" + "=" * 80)
    print(f"  DELTAS (+intradía − base)")
    print("=" * 80)
    print(f"    Δ AUC primario:  {r_id['auc_primary'] - r_base['auc_primary']:+.4f}  "
          f"(base {r_base['auc_primary']:.4f} → {r_id['auc_primary']:.4f})")
    print(f"    Δ AUC meta:      {r_id['auc_meta']    - r_base['auc_meta']:+.4f}")
    print(f"    Δ Sharpe:        {r_id['sharpe']    - r_base['sharpe']:+.3f}")
    print(f"    Δ Retorno total: {r_id['total_ret'] - r_base['total_ret']:+.1f} pts")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
