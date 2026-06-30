"""
Pipeline de evaluación unificado — exporta data/eval/dashboard_eval.json
para el dashboard Streamlit y canvases.

Incluye:
  - Backtest top-K (default + grid search)
  - Métricas duales KB-001
  - Calibración agente (live_stats)
  - LSTM vs LGBM (opcional, --skip-lstm)

Uso:
    ./venv/bin/python scripts/run_all_evaluations.py
    ./venv/bin/python scripts/run_all_evaluations.py --skip-lstm
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.backtest_topk import train_and_backtest
from scripts.evaluate_portfolio import build_portfolio_export

EVAL_DIR = ROOT / "data" / "eval"
OUT_PATH = EVAL_DIR / "dashboard_eval.json"

GRID_VARIANTS = [
    {"top_k": 3, "score_mode": "p_up", "weight_mode": "equal"},
    {"top_k": 5, "score_mode": "p_up", "weight_mode": "equal"},
    {"top_k": 3, "score_mode": "p_rel", "weight_mode": "equal"},
    {"top_k": 5, "score_mode": "p_rel", "weight_mode": "conviction"},
    {"top_k": 3, "score_mode": "signal", "weight_mode": "equal"},
]


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _run_calibrate() -> dict:
    py = ROOT / "venv" / "bin" / "python"
    subprocess.run([str(py), str(ROOT / "scripts" / "calibrate_agent.py")], check=False, cwd=ROOT)
    try:
        from src.ml.knowledge_loader import load_agent_knowledge
        kb = load_agent_knowledge()
        return {
            "calibration": kb.get("calibration", {}),
            "literature_rules_count": len(
                (kb.get("literature_rules") or {}).get("rules", [])
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _grid_search(universe: str = "bmv") -> list[dict]:
    rows: list[dict] = []
    for v in GRID_VARIANTS:
        print(f"  Grid: K={v['top_k']} score={v['score_mode']} weight={v['weight_mode']} …")
        bt = train_and_backtest(universe=universe, **v)
        s = bt["strategy"]
        b = bt["benchmark_naftrac"]
        rows.append({
            **v,
            "sharpe_gross": round(s["sharpe_gross"], 3),
            "sharpe_net": round(s["sharpe_net"], 3),
            "total_return_net": round(s["total_return_net"], 4),
            "max_drawdown": round(s["max_drawdown"], 4),
            "win_rate_net": round(s["win_rate_net"], 3),
            "auc": bt.get("model", {}).get("auc"),
            "vs_naftrac_sharpe": round(s["sharpe_net"] - b["sharpe_ratio"], 3),
        })
    rows.sort(key=lambda r: r["sharpe_net"], reverse=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="bmv")
    parser.add_argument("--skip-lstm", action="store_true")
    parser.add_argument("--skip-grid", action="store_true")
    args = parser.parse_args()

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    print("\n=== Evaluaciones BMV — pipeline unificado ===\n")

    # Default backtest
    print("1/4 Backtest top-K default (K=5, p_up)…")
    default_bt = train_and_backtest(universe=args.universe, top_k=5)
    (EVAL_DIR / "backtest_topk.json").write_text(
        json.dumps(default_bt, indent=2, default=str)
    )
    portfolio = build_portfolio_export(default_bt)
    (EVAL_DIR / "portfolio_metrics.json").write_text(json.dumps(portfolio, indent=2))

    # Grid search
    grid: list[dict] = []
    if not args.skip_grid:
        print("2/4 Grid search backtest…")
        grid = _grid_search(args.universe)
    else:
        print("2/4 Grid search — omitido")

    # Calibrate agent
    print("3/4 Calibración agente…")
    agent_kb = _run_calibrate()

    # LSTM compare
    lstm_data = _load_json(EVAL_DIR / "lstm_vs_lgbm.json")
    if not args.skip_lstm:
        print("4/4 LSTM vs LGBM (--fast: 2 folds, 8 epochs, 12k muestras)…")
        py = ROOT / "venv" / "bin" / "python"
        rc = subprocess.run(
            [str(py), str(ROOT / "scripts" / "compare_lstm_lgbm.py"), "--fast"],
            cwd=ROOT,
        ).returncode
        if rc == 0:
            lstm_data = _load_json(EVAL_DIR / "lstm_vs_lgbm.json")
        else:
            print("   LSTM compare falló — usando JSON previo si existe")
    else:
        print("4/4 LSTM compare — omitido (usa compare_lstm_lgbm.py aparte)")

    best = grid[0] if grid else None
    s = default_bt["strategy"]
    b = default_bt["benchmark_naftrac"]

    dashboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": args.universe,
        "summary": {
            "verdict": "NO_BET_LIVE" if s["sharpe_net"] < 0 else "PAPER_OK",
            "message": (
                "Sharpe neto negativo — no apostar en vivo hasta tunear umbrales/K."
                if s["sharpe_net"] < 0
                else "Edge neto positivo en backtest default."
            ),
            "sharpe_gross": round(s["sharpe_gross"], 3),
            "sharpe_net": round(s["sharpe_net"], 3),
            "total_return_net_pct": round(s["total_return_net"] * 100, 2),
            "benchmark_sharpe": round(b["sharpe_ratio"], 3),
            "benchmark_return_pct": round(b["total_return"] * 100, 2),
            "round_trip_cost_pct": round(default_bt["config"]["round_trip_cost"] * 100, 2),
            "auc": default_bt.get("model", {}).get("auc"),
            "n_periods": s["n_periods"],
            "test_range": [
                default_bt.get("model", {}).get("test_start"),
                default_bt.get("model", {}).get("test_end"),
            ],
        },
        "default_backtest": portfolio,
        "grid_search": grid,
        "best_variant": best,
        "lstm_vs_lgbm": lstm_data,
        "agent_knowledge": agent_kb,
        "implemented_kbs": [
            "KB-001", "KB-003", "KB-004", "KB-010", "KB-011", "KB-012",
            "KB-013", "KB-020", "KB-041", "KB-043", "KB-060", "KB-081",
        ],
        "equity_curves": {
            "net": default_bt["curves"]["net"][-20:],
            "naftrac": default_bt["curves"]["naftrac"][-20:],
        },
    }

    OUT_PATH.write_text(json.dumps(dashboard, indent=2, default=str))
    print(f"\n✅ Exportado: {OUT_PATH}")
    if best:
        print(
            f"   Mejor grid: K={best['top_k']} {best['score_mode']} "
            f"→ Sharpe net {best['sharpe_net']}"
        )
    print(f"   Default Sharpe net: {s['sharpe_net']:.3f} vs NAFTRAC {b['sharpe_ratio']:.3f}\n")


if __name__ == "__main__":
    main()
