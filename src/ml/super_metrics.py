"""
Métricas e incertidumbres del SuperModel — para ingestión del agente Gemini.

Cada ticker recibe un bloque `metrics` con:
  - Calidad OOS por modelo (AUC + IC 90% bootstrap)
  - Convicción fusionada + intervalo heurístico
  - Consenso / desacuerdo entre modelos base
  - Régimen con probabilidades HMM
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

# Modelos núcleo L1 (fusión L2)
CORE_MODELS: tuple[str, ...] = ("xs_lgbm", "ensemble", "heuristic", "lstm_seq")
OPTIONAL_MODELS: tuple[str, ...] = ("woe_abs",)

MODEL_LABELS: dict[str, str] = {
    "xs_lgbm": "LGBM cross-sectional (rank vs universo)",
    "ensemble": "Ensemble WoE+LR+LightGBM (P vs mediana)",
    "heuristic": "Screener técnico normalizado",
    "lstm_seq": "LSTM secuencial P(outperform)",
    "woe_abs": "Ensemble direccional absoluto P(subida)",
}


def bootstrap_auc_ci(
    y: np.ndarray,
    p: np.ndarray,
    *,
    n_boot: int = 150,
    alpha: float = 0.10,
    seed: int = 42,
) -> dict[str, float]:
    """
    AUC en holdout + intervalo de confianza percentil bootstrap.

    Returns
    -------
    {auc, ci_low, ci_high, ci_level, n, std}
    """
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    y, p = y[mask], p[mask]
    n = len(y)
    out: dict[str, float] = {
        "auc": 0.5,
        "ci_low": 0.5,
        "ci_high": 0.5,
        "ci_level": 1.0 - alpha,
        "n": float(n),
        "std": 0.0,
    }
    if n < 30 or len(np.unique(y)) < 2:
        return out

    try:
        point = float(roc_auc_score(y, p))
    except Exception:
        return out

    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        try:
            boots.append(float(roc_auc_score(y[idx], p[idx])))
        except Exception:
            continue

    if not boots:
        out["auc"] = round(point, 4)
        return out

    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    out.update({
        "auc": round(point, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "std": round(float(np.std(boots)), 4),
    })
    return out


def compute_universe_model_metrics(
    valid_preds: dict[str, np.ndarray],
    y_rel: np.ndarray,
    auc_point: dict[str, float],
    *,
    models: list[str] | None = None,
) -> dict[str, dict]:
    """Métricas OOS por modelo en el universo."""
    model_list = models or list(valid_preds.keys())
    metrics: dict[str, dict] = {}
    for name in model_list:
        if name not in valid_preds:
            continue
        ci = bootstrap_auc_ci(y_rel, valid_preds[name])
        auc = float(auc_point.get(name, ci["auc"]))
        edge = auc - 0.5
        metrics[name] = {
            "label": MODEL_LABELS.get(name, name),
            "auc": round(auc, 4),
            "auc_ci_90": [ci["ci_low"], ci["ci_high"]],
            "auc_std": ci["std"],
            "edge_vs_random": round(edge, 4),
            "n_holdout": int(ci["n"]),
            "in_fusion": name in CORE_MODELS,
        }
    return metrics


def compute_fusion_metrics(
    *,
    stack_auc: float,
    fusion_auc: float,
    use_stacking: bool,
    y_rel: np.ndarray,
    stack_scores: np.ndarray | None = None,
) -> dict[str, Any]:
    """Calidad de la capa L2 (stacking vs AUC-weight)."""
    meta: dict[str, Any] = {
        "mode": "stacking" if use_stacking else "auc_weight",
        "stack_auc": round(stack_auc, 4),
        "auc_weight_auc": round(fusion_auc, 4),
        "selected": "stacking" if use_stacking else "auc_weight",
        "delta_auc": round(stack_auc - fusion_auc, 4),
    }
    if stack_scores is not None and use_stacking:
        ci = bootstrap_auc_ci(y_rel, stack_scores)
        meta["stack_auc_ci_90"] = [ci["ci_low"], ci["ci_high"]]
    return meta


def compute_ticker_metrics(
    *,
    signals: dict[str, float],
    conviction_raw: float,
    conviction_adj: float,
    disagreement: float,
    model_weights: dict[str, float],
    model_metrics: dict[str, dict],
    regime_info: dict,
    rank_global: int | None = None,
    n_universe: int | None = None,
    bullish_threshold: float = 0.52,
) -> dict[str, Any]:
    """
    Incertidumbre y consenso por ticker para el agente.

    Intervalo de convicción: heurístico ± 1.96 × disagreement / √n_models
    (proxy epistémico cuando no hay ensemble de preds calibradas).
    """
    base = {m: signals[m] for m in CORE_MODELS if m in signals}
    n_models = len(base) or len(signals)
    bullish = sum(1 for v in base.values() if v >= bullish_threshold)
    bearish = sum(1 for v in base.values() if v <= (1 - bullish_threshold + 0.02))

    se = disagreement / max(np.sqrt(max(n_models, 1)), 1.0)
    half_width = 1.96 * se
    conv_lo = max(0.0, conviction_raw - half_width)
    conv_hi = min(1.0, conviction_raw + half_width)

    # Peso efectivo por modelo en la fusión
    per_model: dict[str, dict] = {}
    for name, score in signals.items():
        mm = model_metrics.get(name, {})
        per_model[name] = {
            "score": round(score, 4),
            "weight": round(model_weights.get(name, 0.0), 3),
            "auc": mm.get("auc"),
            "auc_ci_90": mm.get("auc_ci_90"),
            "edge_vs_random": mm.get("edge_vs_random"),
        }

    regime_proba = regime_info.get("proba") or {}
    regime_entropy = 0.0
    if regime_proba:
        probs = [max(float(v), 1e-9) for v in regime_proba.values()]
        regime_entropy = round(-sum(p * np.log(p) for p in probs), 3)

    return {
        "conviction": {
            "point": round(conviction_adj, 4),
            "raw": round(conviction_raw, 4),
            "ci_90": [round(conv_lo, 4), round(conv_hi, 4)],
            "method": "disagreement_heuristic",
        },
        "consensus": {
            "n_models_active": n_models,
            "n_bullish": bullish,
            "n_bearish": bearish,
            "agreement_pct": round(bullish / max(n_models, 1), 3),
            "disagreement_std": round(disagreement, 4),
        },
        "models": per_model,
        "regime": {
            "state": regime_info.get("estado", "unknown"),
            "proba": regime_proba,
            "entropy": regime_entropy,
        },
        "rank": {
            "global": rank_global,
            "n_universe": n_universe,
        },
    }


def build_model_registry(active_models: set[str]) -> dict[str, Any]:
    """Resumen de arquitectura para el prompt del agente."""
    return {
        "n_core": len(CORE_MODELS),
        "core_models": [
            {
                "id": m,
                "label": MODEL_LABELS[m],
                "active": m in active_models,
            }
            for m in CORE_MODELS
        ],
        "optional_models": [
            {
                "id": m,
                "label": MODEL_LABELS[m],
                "active": m in active_models,
            }
            for m in OPTIONAL_MODELS
        ],
        "n_active_total": len(active_models),
    }


def enrich_ranking_item(item: dict, universe_meta: dict) -> dict:
    """Adjunta `metrics` a un item del master_ranking si aún no existe."""
    if "metrics" in item:
        return item
    slug = item.get("universe_slug", "")
    um = universe_meta.get(slug, {})
    model_metrics = um.get("models", {})
    item["metrics"] = compute_ticker_metrics(
        signals=item.get("signals", {}),
        conviction_raw=float(item.get("conviction_raw", item.get("conviction", 0.5))),
        conviction_adj=float(item.get("conviction", 0.5)),
        disagreement=float(item.get("disagreement", 0)),
        model_weights=item.get("model_weights", {}),
        model_metrics=model_metrics,
        regime_info={
            "estado": item.get("regime", "unknown"),
            "proba": um.get("regime_proba", {}),
        },
        rank_global=item.get("rank_global"),
        n_universe=um.get("n_tickers"),
    )
    return item


def format_metrics_for_prompt(item: dict) -> str:
    """Bloque de texto estructurado para Gemini."""
    m = item.get("metrics") or {}
    conv = m.get("conviction", {})
    cons = m.get("consensus", {})
    lines = [
        f"  Convicción: {conv.get('point')} (IC90: {conv.get('ci_90')}, raw {conv.get('raw')})",
        f"  Consenso: {cons.get('n_bullish')}/{cons.get('n_models_active')} modelos alcistas "
        f"(desacuerdo σ={cons.get('disagreement_std')})",
    ]
    regime = m.get("regime", {})
    if regime.get("proba"):
        proba_s = ", ".join(f"{k}={v:.0%}" for k, v in regime["proba"].items())
        lines.append(f"  Régimen: {regime.get('state')} ({proba_s})")
    lines.append("  Modelos (score | AUC [IC90]):")
    for name, md in (m.get("models") or {}).items():
        label = MODEL_LABELS.get(name, name)
        auc = md.get("auc", "?")
        ci = md.get("auc_ci_90") or ["?", "?"]
        if not isinstance(ci, (list, tuple)) or len(ci) < 2:
            ci = ["?", "?"]
        lines.append(
            f"    · {label} ({name}): score={md.get('score')}  weight={md.get('weight')}  "
            f"AUC={auc} [{ci[0]}–{ci[1]}]"
        )
    return "\n".join(lines)
