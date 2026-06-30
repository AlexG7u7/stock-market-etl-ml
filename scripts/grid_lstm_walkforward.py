#!/usr/bin/env python3
"""
Grid walk-forward LSTM — ticket 2.

Busca mejor sequence_length × epochs × hidden_units vs xs_lgbm baseline.

Uso:
    python scripts/grid_lstm_walkforward.py
    python scripts/grid_lstm_walkforward.py --fast
    python scripts/grid_lstm_walkforward.py --tickers WALMEX ALSEA
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from src.data.universes import BMV_ACCIONES
from src.ml.purged_cv import grid_lstm_walkforward

DEFAULT_GRID = [
    {"sequence_length": 30, "epochs": 40, "hidden_units": 64, "num_layers": 2, "batch_size": 32},
    {"sequence_length": 60, "epochs": 40, "hidden_units": 64, "num_layers": 2, "batch_size": 32},
    {"sequence_length": 30, "epochs": 80, "hidden_units": 128, "num_layers": 2, "batch_size": 32},
    {"sequence_length": 60, "epochs": 60, "hidden_units": 128, "num_layers": 2, "batch_size": 64},
]

FAST_GRID = [
    {"sequence_length": 30, "epochs": 6, "hidden_units": 32, "num_layers": 1, "batch_size": 128},
    {"sequence_length": 60, "epochs": 6, "hidden_units": 32, "num_layers": 1, "batch_size": 128},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTM hyperparam grid — purged walk-forward")
    parser.add_argument("--tickers", nargs="+", default=["WALMEX", "ALSEA", "GMEXICOB"])
    parser.add_argument("--splits", type=int, default=4)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    grid = FAST_GRID if args.fast else DEFAULT_GRID
    max_samples = args.max_samples if args.max_samples else (5000 if args.fast else 12000)

    print(f"\n══ LSTM Grid Walk-Forward — {len(grid)} configs × {len(args.tickers)} tickers ══")
    print(f"   splits={args.splits}  max_samples={max_samples}\n")

    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grid_size": len(grid),
        "tickers": {},
        "best_per_ticker": {},
    }

    for ticker in args.tickers:
        print(f"── {ticker} ──")
        res = grid_lstm_walkforward(
            ticker, BMV_ACCIONES, grid,
            n_splits=2 if args.fast else args.splits,
            max_samples=max_samples,
        )
        out["tickers"][ticker] = res
        best = res.get("best")
        if best:
            out["best_per_ticker"][ticker] = best
            print(
                f"  best: seq={best['sequence_length']} ep={best['epochs']} "
                f"hidden={best['hidden_units']} → LSTM AUC {best['lstm_mean_auc']:.4f} "
                f"(LGBM {best['lgbm_mean_auc']:.4f}, wins {best['lstm_wins']}/{best['n_folds']})"
            )
        else:
            print("  sin resultados")

    path = ROOT / "data" / "eval" / "lstm_grid_walkforward.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n✅ Guardado: {path}\n")


if __name__ == "__main__":
    main()
