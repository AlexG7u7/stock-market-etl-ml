"""
¿Ayuda la IA (redes neuronales) a mejorar el modelo?

Test honesto: ¿una red neuronal encuentra señal que el ensemble (LR+LGBM) no ve?
Si la red NO supera al ensemble, el cuello de botella es la INFORMACIÓN
(los datos no contienen más señal), no la capacidad del modelo — y entonces
la IA solo ayudaría trayendo datos NUEVOS (ej. noticias vía LLM).

Compara AUC en test (hold-out 20%):
  - LightGBM (referencia del ensemble actual)
  - MLP pequeña      (64)
  - MLP profunda     (128, 64, 32)
  - MLP regularizada (128, 64) + alpha alto

Ejecución:
    python scripts/ai_test.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from scripts.run_meta import build_dataset
from src.ml.features  import FEATURE_COLS

TRAIN_RATIO = 0.80


def main():
    print("\n" + "=" * 70)
    print("  ¿Ayuda la IA (redes neuronales)?  |  AUC en hold-out 20%")
    print("=" * 70 + "\n")

    print("[1] Construyendo dataset (horizonte 5)...")
    df = build_dataset(horizon=5).sort_index()
    cut_date = df.index[int(len(df) * TRAIN_RATIO)]
    train = df[df.index < cut_date]
    test  = df[df.index >= cut_date]
    print(f"    Train: {len(train):,}   Test: {len(test):,}")

    # Matriz de features (escaladas + imputadas) — la red aprende sus transformaciones
    imp = SimpleImputer(strategy="median")
    sc  = StandardScaler()
    X_tr = sc.fit_transform(imp.fit_transform(train[FEATURE_COLS]))
    X_te = sc.transform(imp.transform(test[FEATURE_COLS]))
    y_tr = train["y"].values
    y_te = test["y"].values

    print("\n[2] Entrenando modelos...\n")
    results = {}

    # Referencia: LightGBM (lo que usa el ensemble)
    try:
        import lightgbm as lgb
        m = lgb.LGBMClassifier(n_estimators=300, num_leaves=55, learning_rate=0.026,
                               min_child_samples=59, reg_lambda=8.6, verbosity=-1, n_jobs=2)
        m.fit(X_tr, y_tr)
        auc = roc_auc_score(y_te, m.predict_proba(X_te)[:, 1])
        results["LightGBM (ref. ensemble)"] = auc
        print(f"  LightGBM (ref. ensemble):   AUC = {auc:.4f}")
    except ImportError:
        pass

    nets = {
        "MLP pequeña (64)":          dict(hidden_layer_sizes=(64,),       alpha=1e-3),
        "MLP profunda (128,64,32)":  dict(hidden_layer_sizes=(128,64,32), alpha=1e-3),
        "MLP regularizada (128,64)": dict(hidden_layer_sizes=(128,64),    alpha=1e-1),
    }
    for name, kw in nets.items():
        net = MLPClassifier(max_iter=120, early_stopping=True, n_iter_no_change=8,
                            random_state=42, **kw)
        net.fit(X_tr, y_tr)
        auc = roc_auc_score(y_te, net.predict_proba(X_te)[:, 1])
        results[name] = auc
        print(f"  {name:<27} AUC = {auc:.4f}")

    # ── Veredicto ───────────────────────────────────────────────────────────────
    best_net = max((v for k, v in results.items() if "MLP" in k), default=0)
    ref = results.get("LightGBM (ref. ensemble)", 0.5)

    print("\n" + "=" * 70)
    print("  VEREDICTO")
    print("=" * 70)
    print(f"\n  Mejor red neuronal: {best_net:.4f}   |   LightGBM: {ref:.4f}")
    if best_net <= ref + 0.005:
        print("\n  → La red NO supera al ensemble (diferencia despreciable).")
        print("    El cuello de botella es la INFORMACIÓN, no el modelo.")
        print("    La IA solo ayudaría trayendo datos NUEVOS (ej. noticias vía LLM).")
    else:
        print(f"\n  → La red mejora {(best_net-ref)*100:+.2f} pts de AUC. Vale la pena explorar deep learning.")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
