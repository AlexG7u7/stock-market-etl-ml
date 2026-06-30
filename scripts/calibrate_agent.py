#!/usr/bin/env python3
"""
Calibrate agent live stats from paper trades and update knowledge YAML.

Usage:
    python scripts/calibrate_agent.py
    python scripts/calibrate_agent.py --paper-trades data/paper_trades.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
CALIBRATION_PATH = PROJECT_ROOT / "articles" / "knowledge" / "agent" / "calibration.yaml"
PERFORMANCE_LOG_PATH = PROJECT_ROOT / "articles" / "knowledge" / "agent" / "performance_log.yaml"
DEFAULT_PAPER_TRADES = PROJECT_ROOT / "data" / "paper_trades.json"

CLOSED_STATUSES = frozenset({"T2_HIT", "STOP_HIT", "EXPIRED"})


def _load_paper_trades(path: Path) -> dict:
    if not path.exists():
        return {"trades": [], "initial_capital": 100_000.0}
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_live_stats(trades: list[dict]) -> dict | None:
    closed = [t for t in trades if t.get("status") in CLOSED_STATUSES]
    if not closed:
        return None

    wins = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_pct") or 0) <= 0]

    win_rate = len(wins) / len(closed)
    avg_win_pct = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
    avg_loss_pct = float(np.mean([abs(t["pnl_pct"]) for t in losses])) if losses else 0.0

    pnl_rets = [t.get("pnl_pct", 0.0) for t in closed]
    sharpe_approx = float(
        (np.mean(pnl_rets) / (np.std(pnl_rets) + 1e-8)) * np.sqrt(52)
    )

    return {
        "source": "paper_trades",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "n_closed": len(closed),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "payoff_ratio": round(avg_win_pct / (avg_loss_pct + 1e-8), 2),
        "sharpe_approx": round(sharpe_approx, 3),
    }


def _estimated_from_risk_engine() -> dict:
    from src.ml.risk_engine import HIST_AVG_LOSS, HIST_AVG_WIN, HIST_WIN_RATE

    return {
        "source": "estimated_from_risk_engine",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "n_closed": 0,
        "win_rate": HIST_WIN_RATE,
        "avg_win_pct": HIST_AVG_WIN,
        "avg_loss_pct": HIST_AVG_LOSS,
        "payoff_ratio": round(HIST_AVG_WIN / HIST_AVG_LOSS, 2),
        "sharpe_approx": None,
        "note": "No closed paper trades yet; using walk-forward constants from risk_engine",
    }


def update_calibration_yaml(live_stats: dict) -> None:
    with CALIBRATION_PATH.open(encoding="utf-8") as f:
        cal = yaml.safe_load(f) or {}

    cal["live_stats"] = live_stats
    cal.setdefault("meta", {})["last_updated"] = live_stats["updated_at"]

    with CALIBRATION_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(cal, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def update_performance_log(live_stats: dict, trades: list[dict]) -> None:
    if PERFORMANCE_LOG_PATH.exists():
        with PERFORMANCE_LOG_PATH.open(encoding="utf-8") as f:
            log = yaml.safe_load(f) or {}
    else:
        log = {
            "meta": {
                "schema_version": "1.0",
                "description": "Weekly performance history for agent calibration",
            },
            "entries": [],
        }

    week_label = datetime.now(timezone.utc).strftime("%Y-W%W")
    entry = {
        "week": week_label,
        "updated_at": live_stats["updated_at"],
        "source": live_stats["source"],
        "n_closed": live_stats.get("n_closed", 0),
        "n_open_pending": sum(
            1 for t in trades if t.get("status") in ("PENDING", "OPEN", "T1_HIT")
        ),
        "win_rate": live_stats.get("win_rate"),
        "avg_win_pct": live_stats.get("avg_win_pct"),
        "avg_loss_pct": live_stats.get("avg_loss_pct"),
        "sharpe_approx": live_stats.get("sharpe_approx"),
        "payoff_ratio": live_stats.get("payoff_ratio"),
    }

    entries: list = log.setdefault("entries", [])
    entries = [e for e in entries if e.get("week") != week_label]
    entries.append(entry)
    log["entries"] = entries[-52:]

    with PERFORMANCE_LOG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(log, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate agent knowledge from paper trades")
    parser.add_argument(
        "--paper-trades",
        type=Path,
        default=DEFAULT_PAPER_TRADES,
        help="Path to paper_trades.json",
    )
    args = parser.parse_args()

    data = _load_paper_trades(args.paper_trades)
    trades = data.get("trades", [])
    live_stats = _compute_live_stats(trades) or _estimated_from_risk_engine()

    update_calibration_yaml(live_stats)
    update_performance_log(live_stats, trades)

    print(f"Calibration updated: source={live_stats['source']}")
    print(f"  win_rate={live_stats.get('win_rate')}, "
          f"avg_win={live_stats.get('avg_win_pct')}%, "
          f"avg_loss={live_stats.get('avg_loss_pct')}%, "
          f"sharpe≈{live_stats.get('sharpe_approx')}")
    print(f"  → {CALIBRATION_PATH}")
    print(f"  → {PERFORMANCE_LOG_PATH}")


if __name__ == "__main__":
    main()
