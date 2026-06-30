"""
Política operativa de apuestas — derivada de experimentos P0 (2026-06-29).

Fuente: data/eval/experiments.json
  - Stacking LR > AUC-weight (Sharpe -1.66 vs -2.02)
  - Mejor grid robusto: K=2, min_p_up=0.56 (67 períodos)
  - News A/B sin uplift → no usar news en features hasta backfill histórico
  - Veredicto: PAPER_ONLY (Sharpe neto robusto < 0)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_JSON = ROOT / "data" / "eval" / "bet_policy.json"

# ── Defaults post-experimentos ───────────────────────────────────────────────
PAPER_ONLY: bool = True
LIVE_TRADING_ALLOWED: bool = False

USE_STACKING_DEFAULT: bool = True
USE_NEWS_FEATURES: bool = False  # ΔAUC=0 con cache estático por ticker
MIN_NEWS_PANEL_TICKERS: int = 3  # activar panel temporal cuando backfill ≥ esto

MAX_SIGNALS: int = 2
MAX_OPEN_POSITIONS: int = 2
MAX_DAILY_NEW_BETS: int = 2

PROB_THRESH_BASE: float = 0.56
PROB_THRESH_BULL: float = 0.54
PROB_THRESH_BEAR: float = 0.58
PROB_THRESH_LATERAL: float = 0.56

MIN_CONVICTION: float = 0.56  # SuperModel master_ranking
KELLY_FRAC: float = 0.25
MAX_POSITION_PCT: float = 0.10

BACKTEST_TOP_K: int = 2
BACKTEST_MIN_P_UP: float = 0.56


def news_features_enabled(stats: dict | None = None) -> bool:
    """
    News en features cuando hay panel temporal con cobertura suficiente (KB-004)
    o cuando USE_NEWS_FEATURES=True explícitamente.
    """
    if USE_NEWS_FEATURES:
        return True
    if stats is None:
        try:
            from src.ml.news_history import history_stats

            stats = history_stats()
        except Exception:
            return False
    if stats.get("status") == "missing":
        try:
            from src.ml.databursatil_news import list_snapshot_dates

            if len(list_snapshot_dates()) >= MIN_NEWS_PANEL_TICKERS:
                return True
        except Exception:
            pass
        return False
    if int(stats.get("tickers") or 0) >= MIN_NEWS_PANEL_TICKERS:
        return True
    if int(stats.get("n_days") or stats.get("rows") or 0) >= MIN_NEWS_PANEL_TICKERS:
        return True
    return False


def prob_thresh_for_regime(state: str | None) -> float:
    """Umbral P(up) / convicción según régimen HMM."""
    s = (state or "lateral").lower()
    if s == "bull":
        return PROB_THRESH_BULL
    if s == "bear":
        return PROB_THRESH_BEAR
    return PROB_THRESH_LATERAL


def filter_actionable_ranking(
    ranking: list[dict],
    *,
    max_signals: int | None = None,
    min_conviction: float | None = None,
    require_gemini_confirms: bool = True,
) -> list[dict]:
    """
    Filtra master_ranking para apuestas paper según política post-exp.

    Excluye VETA Gemini; opcionalmente solo CONFIRMA/DEGRADA con convicción ≥ umbral.
    """
    max_k = max_signals if max_signals is not None else MAX_SIGNALS
    min_c = min_conviction if min_conviction is not None else MIN_CONVICTION
    out: list[dict] = []

    for item in ranking:
        if len(out) >= max_k:
            break
        conv = float(item.get("conviction") or item.get("conviction_raw") or 0)
        if conv < min_c:
            continue
        g = item.get("gemini") or {}
        ver = g.get("veredicto", "")
        if require_gemini_confirms and ver in ("VETA", "EVITAR"):
            continue
        if require_gemini_confirms and ver and ver not in (
            "CONFIRMA", "DEGRADA", "APOSTAR", "ESPERAR",
        ):
            continue
        out.append(item)
    return out


def export_policy_json(path: Path | None = None) -> Path:
    """Escribe snapshot JSON para dashboard / agent KB."""
    dest = path or POLICY_JSON
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "experiments P0 2026-06-29",
        "paper_only": PAPER_ONLY,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
        "use_stacking_default": USE_STACKING_DEFAULT,
        "use_news_features": USE_NEWS_FEATURES,
        "max_signals": MAX_SIGNALS,
        "prob_thresh_base": PROB_THRESH_BASE,
        "prob_thresh_bull": PROB_THRESH_BULL,
        "prob_thresh_bear": PROB_THRESH_BEAR,
        "min_conviction": MIN_CONVICTION,
        "backtest_top_k": BACKTEST_TOP_K,
        "backtest_min_p_up": BACKTEST_MIN_P_UP,
        "recommendation": "K=2 min_p=0.56 stacking ON paper only",
    }
    dest.write_text(json.dumps(payload, indent=2))
    return dest


def load_policy_overrides() -> dict:
    """Carga overrides desde bet_policy.json si existe."""
    if not POLICY_JSON.exists():
        return {}
    try:
        return json.loads(POLICY_JSON.read_text())
    except Exception:
        return {}
