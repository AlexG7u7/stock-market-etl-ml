"""
Compara xs_lgbm vs lstm_seq en tickers BMV con Purged Walk-Forward CV.

Ejecución:
    python scripts/compare_lstm_lgbm.py
    python scripts/compare_lstm_lgbm.py --epochs 12 --splits 3

Exporta: data/eval/lstm_vs_lgbm.json
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
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

try:
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(1)
    tf.config.threading.set_inter_op_parallelism_threads(1)
except Exception:
    pass

from src.data.universes import BMV_ACCIONES
from src.ml.purged_cv import compare_lstm_vs_lgbm

COMPARE_TICKERS = ["WALMEX", "ALSEA", "GMEXICOB"]


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTM-seq vs xs_lgbm purged CV")
    parser.add_argument("--splits", type=int, default=6, help="Walk-forward folds")
    parser.add_argument("--epochs", type=int, default=40, help="LSTM epochs por fold")
    parser.add_argument(
        "--max-samples", type=int, default=None,
        help="Máx secuencias LSTM por fold (subsample). Default: 12000 en --fast",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Modo rápido: 2 folds, 8 epochs, max 12000 muestras",
    )
    parser.add_argument("--embargo", type=int, default=10)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument(
        "--tickers", nargs="+", default=COMPARE_TICKERS,
        help="Tickers BMV a comparar",
    )
    args = parser.parse_args()

    if args.fast:
        args.splits = min(args.splits, 2)
        args.epochs = min(args.epochs, 6)
        if args.max_samples is None:
            args.max_samples = 5_000

    lstm_layers = 1 if args.fast else 2
    lstm_hidden = 32 if args.fast else 64
    lstm_batch = 128 if args.fast else 32

    print("\n" + "=" * 65)
    print("  LSTM-seq vs xs_lgbm  |  Purged Walk-Forward CV")
    print(f"  Tickers: {', '.join(args.tickers)}")
    print(
        f"  {args.splits} folds  |  embargo={args.embargo}d  |  "
        f"horizonte={args.horizon}d  |  LSTM epochs={args.epochs}"
        + (f"  |  max_samples={args.max_samples}" if args.max_samples else "")
    )
    print("=" * 65 + "\n")

    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "n_splits": args.splits,
            "lstm_epochs": args.epochs,
            "lstm_max_samples": args.max_samples,
            "fast_mode": args.fast,
            "embargo": args.embargo,
            "horizon": args.horizon,
        },
        "tickers": {},
        "summary": [],
    }

    for ticker in args.tickers:
        print(f"\n── {ticker} ──")
        try:
            res = compare_lstm_vs_lgbm(
                ticker=ticker,
                universe=BMV_ACCIONES,
                n_splits=args.splits,
                horizon=args.horizon,
                embargo=args.embargo,
                lstm_epochs=args.epochs,
                lstm_max_samples=args.max_samples,
                lstm_num_layers=lstm_layers,
                lstm_hidden_units=lstm_hidden,
                lstm_batch_size=lstm_batch,
            )
        except Exception as exc:
            print(f"  Error: {exc}")
            results["tickers"][ticker] = {"error": str(exc)}
            continue

        results["tickers"][ticker] = res

        if "aggregate" in res:
            agg = res["aggregate"]
            print(
                f"  xs_lgbm AUC:  {agg['xs_lgbm_mean_auc']:.4f} "
                f"± {agg['xs_lgbm_std_auc']:.4f}"
            )
            print(
                f"  lstm_seq AUC: {agg['lstm_seq_mean_auc']:.4f} "
                f"± {agg['lstm_seq_std_auc']:.4f}  "
                f"(wins {agg['lstm_wins']}/{agg['n_folds']} folds)"
            )
            results["summary"].append({
                "ticker": ticker,
                "xs_lgbm_mean_auc": agg["xs_lgbm_mean_auc"],
                "lstm_seq_mean_auc": agg["lstm_seq_mean_auc"],
                "lstm_wins": agg["lstm_wins"],
                "n_folds": agg["n_folds"],
            })
        else:
            print(f"  Sin resultados: {res.get('error', 'unknown')}")

    out_dir = ROOT / "data" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lstm_vs_lgbm.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\n{'=' * 65}")
    print(f"Guardado: {out_path}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
