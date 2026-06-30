"""
Evalúa métricas duales de portafolio (KB-001) y exporta JSON.

Métricas: AUC + Sharpe bruto/neto + MDD + Calmar + win_rate neto.

Uso:
    ./venv/bin/python scripts/evaluate_portfolio.py --universe bmv --top-k 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.backtest_topk import print_summary, train_and_backtest
from src.data.store import UNIVERSE_GROUPS
from src.ml.shared.evaluators.metrics import Metrics

DEFAULT_OUTPUT = ROOT / "data" / "eval" / "portfolio_metrics.json"


def build_portfolio_export(backtest_result: dict) -> dict:
    """Formatea métricas duales KB-001 para exportación."""
    s = backtest_result["strategy"]
    m = backtest_result.get("model", {})
    b = backtest_result["benchmark_naftrac"]
    v = backtest_result["vs_benchmark"]
    cfg = backtest_result["config"]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe": backtest_result.get("universe"),
        "classification": {
            "auc": m.get("auc"),
            "target_col": m.get("target_col"),
        },
        "portfolio_dual": {
            "auc": s.get("auc", m.get("auc")),
            "sharpe_gross": s.get("sharpe_gross"),
            "sharpe_net": s.get("sharpe_net"),
            "max_drawdown": s.get("max_drawdown"),
            "calmar_ratio": s.get("calmar_ratio"),
            "win_rate_net": s.get("win_rate_net"),
            "total_return_gross": s.get("total_return_gross"),
            "total_return_net": s.get("total_return_net"),
        },
        "benchmark_naftrac": {
            "sharpe_ratio": b.get("sharpe_ratio"),
            "max_drawdown": b.get("max_drawdown"),
            "total_return": b.get("total_return"),
            "win_rate": b.get("win_rate"),
        },
        "vs_benchmark": v,
        "costs": {
            "commission_pct": cfg.get("commission_pct"),
            "slippage_pct": cfg.get("slippage_pct"),
            "round_trip_cost": cfg.get("round_trip_cost"),
        },
        "config": {
            "top_k": cfg.get("top_k"),
            "score_mode": cfg.get("score_mode"),
            "weight_mode": cfg.get("weight_mode"),
            "horizon": cfg.get("horizon"),
        },
        "periods": {
            "n_strategy": s.get("n_periods"),
            "n_benchmark": b.get("n_periods"),
            "test_start": m.get("test_start"),
            "test_end": m.get("test_end"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportar métricas duales de portafolio")
    parser.add_argument("--universe", default="bmv", choices=list(UNIVERSE_GROUPS))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--score",
        default="p_up",
        choices=["p_up", "p_rel", "signal"],
    )
    parser.add_argument(
        "--weight",
        default="equal",
        choices=["equal", "conviction"],
    )
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--commission", type=float, default=Metrics.DEFAULT_COMMISSION_PCT)
    parser.add_argument("--slippage", type=float, default=Metrics.DEFAULT_SLIPPAGE_PCT)
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Ruta JSON de salida (default: data/eval/portfolio_metrics.json)",
    )
    args = parser.parse_args()

    backtest = train_and_backtest(
        universe=args.universe,
        top_k=args.top_k,
        score_mode=args.score,
        weight_mode=args.weight,
        horizon=args.horizon,
        commission_pct=args.commission,
        slippage_pct=args.slippage,
    )

    export = build_portfolio_export(backtest)
    print_summary(backtest)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=2, ensure_ascii=False, default=str))
    print(f"\nMétricas duales exportadas: {out_path}")


if __name__ == "__main__":
    main()
