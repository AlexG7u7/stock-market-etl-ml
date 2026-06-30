#!/usr/bin/env python3
"""
Ising challenge — agentes compiten en escenarios sintéticos calibrados con BMV.

Agentes:
  quant      — sigue convicción SuperModel (simulada: momentum del escenario)
  trader     — conservador (solo si magnetización > umbral)
  contrarian — apuesta contra el consenso
  random     — baseline

Uso:
  python scripts/ising_challenge.py
  python scripts/ising_challenge.py --scenarios 200 --steps 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data import store
from src.ml.ising_market import IsingMarket


def _load_bmv_returns(n_cal: int = 252) -> np.ndarray:
    df = store.load("NAFTRAC.MX")
    if df is None or df.empty:
        return np.random.default_rng(42).normal(0, 0.01, n_cal)
    r = np.log(df["Close"] / df["Close"].shift(1)).dropna().values
    return r[-n_cal:] if len(r) >= n_cal else r


def _agent_decision(agent: str, M: float, ret: float, rng: np.random.Generator) -> int:
    """+1 long, 0 flat."""
    if agent == "quant":
        return 1 if M > 0.05 else 0
    if agent == "trader":
        return 1 if M > 0.15 and ret > 0 else 0
    if agent == "contrarian":
        return 1 if M < -0.05 else 0
    if agent == "random":
        return 1 if rng.random() > 0.5 else 0
    return 0


def run_challenge(
    *,
    n_scenarios: int = 100,
    n_steps: int = 20,
    seed: int = 42,
) -> dict:
    cal_returns = pd.Series(_load_bmv_returns())
    market = IsingMarket()
    market.calibrate(cal_returns)

    agents = ("quant", "trader", "contrarian", "random")
    rng = np.random.default_rng(seed)
    scores: dict[str, list[float]] = {a: [] for a in agents}
    hits: dict[str, list[int]] = {a: [] for a in agents}

    for s in range(n_scenarios):
        market.reset(seed=seed + s)
        result = market.simulate(n_steps=n_steps, warmup=10)
        rets = result.log_returns
        mags = result.magnetizations
        for t in range(1, len(rets)):
            M = float(mags[t - 1])
            realized = float(rets[t])
            for agent in agents:
                pos = _agent_decision(agent, M, realized, rng)
                pnl = pos * realized
                scores[agent].append(pnl)
                hits[agent].append(1 if (pos > 0) == (realized > 0) else 0)

    leaderboard = []
    for agent in agents:
        pnl = np.array(scores[agent])
        hr = np.mean(hits[agent]) if hits[agent] else 0.0
        sharpe = float(np.mean(pnl) / (np.std(pnl) + 1e-8) * np.sqrt(252))
        leaderboard.append({
            "agent": agent,
            "n_trades": int(np.sum(np.array(scores[agent]) != 0)),
            "hit_rate": round(hr, 4),
            "mean_pnl": round(float(np.mean(pnl)), 6),
            "sharpe_approx": round(sharpe, 3),
        })
    leaderboard.sort(key=lambda x: x["sharpe_approx"], reverse=True)

    return {
        "n_scenarios": n_scenarios,
        "n_steps": n_steps,
        "calibration_source": "NAFTRAC.MX",
        "leaderboard": leaderboard,
        "winner": leaderboard[0]["agent"] if leaderboard else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ising multi-agent challenge")
    parser.add_argument("--scenarios", type=int, default=100)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--out", default="data/eval/ising_challenge.json")
    args = parser.parse_args()

    print("\n══ Ising Challenge — agentes celulares ══\n")
    result = run_challenge(n_scenarios=args.scenarios, n_steps=args.steps)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    for row in result["leaderboard"]:
        print(
            f"  {row['agent']:<12} hit={row['hit_rate']:.1%}  "
            f"sharpe≈{row['sharpe_approx']:+.2f}  trades={row['n_trades']}"
        )
    print(f"\n  🏆 Ganador: {result['winner']}")
    print(f"  Guardado: {out}\n")


if __name__ == "__main__":
    main()
