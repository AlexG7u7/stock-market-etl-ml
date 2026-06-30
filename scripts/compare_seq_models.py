#!/usr/bin/env python3
"""
A/B/C secuencial: xs_lgbm vs lstm_seq vs tcn_seq — ticket 3 (Dudukcu TCN-LSTM).

Uso:
    python scripts/compare_seq_models.py
    python scripts/compare_seq_models.py --fast
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
from src.ml.purged_cv import compare_seq_models

DEFAULT_TICKERS = ["WALMEX", "ALSEA", "GMEXICOB"]


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTM vs TCN vs LGBM purged CV")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--splits", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--seq-len", type=int, default=30)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--lstm-only", action="store_true")
    parser.add_argument("--tcn-only", action="store_true")
    args = parser.parse_args()

    if args.fast:
        args.splits = 2
        args.epochs = 6

    print(f"\n══ Seq Models A/B/C — {', '.join(args.tickers)} ══")
    print(f"   {args.splits} folds | seq={args.seq_len} | epochs={args.epochs}\n")

    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": vars(args),
        "tickers": {},
        "summary": [],
    }

    for ticker in args.tickers:
        print(f"── {ticker} ──")
        try:
            res = compare_seq_models(
                ticker=ticker,
                universe=BMV_ACCIONES,
                n_splits=args.splits,
                sequence_length=args.seq_len,
                epochs=args.epochs,
                max_samples=5000 if args.fast else 12000,
                lstm_num_layers=1 if args.fast else 2,
                lstm_hidden_units=32 if args.fast else 64,
                include_lstm=not args.tcn_only,
                include_tcn=not args.lstm_only,
            )
        except Exception as exc:
            print(f"  Error: {exc}")
            results["tickers"][ticker] = {"error": str(exc)}
            continue

        results["tickers"][ticker] = res
        agg = res.get("aggregate", {})
        line = f"  LGBM {agg.get('xs_lgbm_mean_auc', 0):.4f}"
        if "lstm_seq_mean_auc" in agg:
            line += f" | LSTM {agg['lstm_seq_mean_auc']:.4f} (wins {agg.get('lstm_wins_vs_lgbm', 0)})"
        if "tcn_seq_mean_auc" in agg:
            line += f" | TCN {agg['tcn_seq_mean_auc']:.4f} (wins {agg.get('tcn_wins_vs_lgbm', 0)})"
        if "best_seq_model" in agg:
            line += f" → best: {agg['best_seq_model']}"
        print(line)
        results["summary"].append({"ticker": ticker, **agg})

    path = ROOT / "data" / "eval" / "seq_models_ab.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\n✅ Guardado: {path}\n")


if __name__ == "__main__":
    main()
