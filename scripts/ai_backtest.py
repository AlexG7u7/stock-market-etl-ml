"""
¿Mejora el bottom-line agregar una RED NEURONAL al ensemble?

El test de AUC (ai_test.py) sugirió que una MLP regularizada sube ~1 pt de AUC.
Aquí medimos lo que importa: el RETORNO del backtest semanal completo
(stack: Ensemble + Meta + Régimen), con y sin la red como tercer votante.

Ejecución:
    python scripts/ai_backtest.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from scripts.run_meta    import build_dataset
from scripts.experiments import train_eval, fmt
from src.ml.features     import FEATURE_COLS


def main():
    print("\n" + "=" * 74)
    print("  ¿Agregar red neuronal al ensemble mejora el RETORNO? (backtest stack)")
    print("=" * 74 + "\n")

    print("[1] Construyendo dataset (horizonte 5)...")
    df = build_dataset(horizon=5)

    print("\n[2] Backtest 2 votantes (LR + LGBM) — producción actual:")
    r2 = train_eval(df, FEATURE_COLS, horizon=5, use_mlp=False)
    print(f"    {fmt(r2)}")

    print("\n[3] Backtest 3 votantes (LR + LGBM + MLP) — TEST DE ROBUSTEZ (10 semillas):")
    print("    Si el resultado solo funciona con una semilla, es suerte, no señal.\n")
    rets, dds, trades, aucs = [], [], [], []
    for seed in range(10):
        r = train_eval(df, FEATURE_COLS, horizon=5, use_mlp=True, mlp_seed=seed)
        rets.append(r["total_ret"]); dds.append(r["max_dd"])
        trades.append(r["n_trades"]); aucs.append(r["auc_primary"])
        print(f"    seed={seed:>2}:  AUC_p={r['auc_primary']:.4f}  trades={r['n_trades']:>3}  "
              f"MaxDD={r['max_dd']:>6.1f}%  TotalRet={r['total_ret']:>+7.1f}%")

    import numpy as np
    rets = np.array(rets)
    print("\n" + "=" * 74)
    print("  VEREDICTO (robustez sobre 10 semillas)")
    print("=" * 74)
    print(f"\n  2 votantes (baseline):  {r2['total_ret']:+.1f}%")
    print(f"  3 votantes (con red):   media={rets.mean():+.1f}%  mediana={np.median(rets):+.1f}%  "
          f"std={rets.std():.1f}  min={rets.min():+.1f}%  max={rets.max():+.1f}%")
    print(f"  Semillas que ganan al baseline: {int((rets > r2['total_ret']).sum())}/10")
    print(f"  Semillas positivas (>0%):       {int((rets > 0).sum())}/10")

    if np.median(rets) > r2["total_ret"] + 1 and (rets > r2["total_ret"]).sum() >= 7:
        print("\n  → ROBUSTO: la red mejora consistentemente. Activar en producción.")
    elif rets.std() > abs(rets.mean()) :
        print("\n  → FRÁGIL: el resultado depende de la semilla (alta varianza). Era suerte.")
    else:
        print("\n  → Mixto: mejora leve pero inestable. No justifica la complejidad extra.")
    print("\n" + "=" * 74 + "\n")


if __name__ == "__main__":
    main()
