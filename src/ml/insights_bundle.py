"""
InsightsBundle — contrato único de producto para dashboard / API.

Unifica SuperModel + métricas con incertidumbre + Gemini trader + bet_policy
en un solo JSON: data/insights_today.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
INSIGHTS_OUT = ROOT / "data" / "insights_today.json"
EVAL_PATH = ROOT / "data" / "eval" / "dashboard_eval.json"
BET_POLICY_PATH = ROOT / "data" / "eval" / "bet_policy.json"

SCHEMA_VERSION = "1.0"
DISCLAIMER = (
    "Insights cuantitativos con incertidumbre estimada. No constituyen "
    "recomendación de inversión; el usuario decide si apuesta. "
    "paper_only hasta validación de edge neto post-costos."
)


class ConvictionMetrics(BaseModel):
    point: float
    raw: float | None = None
    ci_90: list[float] = Field(default_factory=list)
    method: str | None = None


class TickerInsight(BaseModel):
    ticker: str
    universe: str
    universe_slug: str
    moneda: str | None = None
    rank_global: int
    precio: float | None = None
    conviction: float
    conviction_metrics: ConvictionMetrics | None = None
    disagreement: float
    n_models_bullish: int | None = None
    signals: dict[str, float] = Field(default_factory=dict)
    model_weights: dict[str, float] = Field(default_factory=dict)
    fusion_mode: str | None = None
    regime: str | None = None
    regime_proba: dict[str, float] = Field(default_factory=dict)
    news_sent: float | None = None
    news_alerta: bool = False
    horizonte_d: int | None = None
    gemini: dict[str, Any] | None = None
    veredicto: str | None = None
    como_apostar: dict[str, Any] | None = None
    incertidumbres: list[str] = Field(default_factory=list)


class ModelSummary(BaseModel):
    id: str
    label: str
    active: bool
    auc: float | None = None
    auc_ci_90: list[float] = Field(default_factory=list)
    edge_vs_random: float | None = None


class UniverseSummary(BaseModel):
    slug: str
    universe: str
    n_tickers: int
    n_scored: int | None = None
    fusion_mode: str | None = None
    stack_auc: float | None = None
    auc_weight_auc: float | None = None
    models: list[ModelSummary] = Field(default_factory=list)


class PortfolioBrief(BaseModel):
    resumen_ejecutivo: str = ""
    mercado_hoy: str = ""
    apostar: list[str] = Field(default_factory=list)
    esperar: list[str] = Field(default_factory=list)
    evitar: list[str] = Field(default_factory=list)
    allocation_sugerida: dict[str, str] = Field(default_factory=dict)
    riesgos_mercado: list[str] = Field(default_factory=list)
    incertidumbres_globales: list[str] = Field(default_factory=list)
    confianza_portfolio: int | None = None
    fallback: bool = False


class EvalSummary(BaseModel):
    verdict: str | None = None
    message: str | None = None
    sharpe_net: float | None = None
    sharpe_gross: float | None = None
    auc: float | None = None
    benchmark_sharpe: float | None = None
    paper_only: bool = True


class InsightsBundle(BaseModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: str
    disclaimer: str = DISCLAIMER
    n_tickers: int = 0
    model_registry: dict[str, Any] = Field(default_factory=dict)
    universes: list[UniverseSummary] = Field(default_factory=list)
    bet_policy: dict[str, Any] = Field(default_factory=dict)
    eval_summary: EvalSummary | None = None
    gemini_agent: str | None = None
    gemini_summary: dict[str, Any] = Field(default_factory=dict)
    portfolio: PortfolioBrief | None = None
    top_picks: list[TickerInsight] = Field(default_factory=list)
    bmv_actionable: list[TickerInsight] = Field(default_factory=list)
    quantitative_insights: list[dict[str, Any]] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _item_to_insight(item: dict) -> TickerInsight:
    m = item.get("metrics") or {}
    conv_m = m.get("conviction") or {}
    cons = m.get("consensus") or {}
    regime = m.get("regime") or {}
    g = item.get("gemini") or {}

    incert: list[str] = list(g.get("incertidumbres_clave") or [])
    ci = conv_m.get("ci_90")
    if ci and len(ci) == 2:
        incert.append(f"Convicción IC90 [{ci[0]}, {ci[1]}]")
    if cons.get("disagreement_std", 0) > 0.2:
        incert.append(f"Desacuerdo alto σ={cons.get('disagreement_std')}")

    return TickerInsight(
        ticker=item["ticker"],
        universe=item.get("universe", ""),
        universe_slug=item.get("universe_slug", ""),
        moneda=item.get("moneda"),
        rank_global=int(item.get("rank_global", 0)),
        precio=item.get("precio"),
        conviction=float(item.get("conviction", 0)),
        conviction_metrics=ConvictionMetrics(
            point=float(conv_m.get("point", item.get("conviction", 0))),
            raw=conv_m.get("raw"),
            ci_90=list(ci or []),
            method=conv_m.get("method"),
        ) if conv_m else None,
        disagreement=float(item.get("disagreement", 0)),
        n_models_bullish=cons.get("n_bullish"),
        signals=dict(item.get("signals") or {}),
        model_weights=dict(item.get("model_weights") or {}),
        fusion_mode=item.get("fusion_mode"),
        regime=item.get("regime") or regime.get("state"),
        regime_proba=dict(regime.get("proba") or {}),
        news_sent=item.get("news_sent"),
        news_alerta=bool(item.get("news_alerta", False)),
        horizonte_d=item.get("horizonte_d"),
        gemini=g or None,
        veredicto=g.get("veredicto"),
        como_apostar=g.get("como_apostar"),
        incertidumbres=incert,
    )


def _build_universe_summaries(universe_metrics: dict) -> list[UniverseSummary]:
    from src.ml.super_metrics import MODEL_LABELS

    out: list[UniverseSummary] = []
    for slug, um in universe_metrics.items():
        fusion = um.get("fusion") or {}
        models: list[ModelSummary] = []
        for mid, md in (um.get("models") or {}).items():
            models.append(ModelSummary(
                id=mid,
                label=MODEL_LABELS.get(mid, mid),
                active=True,
                auc=md.get("auc"),
                auc_ci_90=list(md.get("auc_ci_90") or []),
                edge_vs_random=md.get("edge_vs_random"),
            ))
        out.append(UniverseSummary(
            slug=slug,
            universe=um.get("universe", slug),
            n_tickers=int(um.get("n_tickers", 0)),
            n_scored=um.get("n_scored"),
            fusion_mode=fusion.get("selected"),
            stack_auc=fusion.get("stack_auc"),
            auc_weight_auc=fusion.get("auc_weight_auc"),
            models=models,
        ))
    return out


def _eval_summary_from_dashboard() -> EvalSummary | None:
    dash = _load_json(EVAL_PATH)
    s = dash.get("summary") or {}
    if not s:
        bp = _load_json(BET_POLICY_PATH)
        if not bp:
            return None
        return EvalSummary(paper_only=bool(bp.get("paper_only", True)))
    return EvalSummary(
        verdict=s.get("verdict"),
        message=s.get("message"),
        sharpe_net=s.get("sharpe_net"),
        sharpe_gross=s.get("sharpe_gross"),
        auc=s.get("auc"),
        benchmark_sharpe=s.get("benchmark_sharpe"),
        paper_only=True,
    )


def build_insights_bundle(
    super_result: dict,
    *,
    top_picks: int = 15,
    bmv_actionable: list[dict] | None = None,
    portfolio: dict | None = None,
) -> InsightsBundle:
    """Construye InsightsBundle desde salida de SuperModel + pipeline."""
    ranking = super_result.get("master_ranking") or []
    with_gemini = [r for r in ranking if r.get("gemini")][:top_picks]
    if not with_gemini:
        with_gemini = ranking[:top_picks]

    actionable_raw = bmv_actionable or super_result.get("actionable_bets_bmv") or []
    gs = super_result.get("gemini_summary") or {}
    portfolio_data = portfolio or super_result.get("portfolio_brief")

    return InsightsBundle(
        generated_at=super_result.get("generated_at")
        or datetime.now(timezone.utc).isoformat(),
        n_tickers=int(super_result.get("n_tickers", len(ranking))),
        model_registry=dict(super_result.get("model_registry") or {}),
        universes=_build_universe_summaries(super_result.get("universe_metrics") or {}),
        bet_policy=dict(super_result.get("bet_policy") or _load_json(BET_POLICY_PATH)),
        eval_summary=_eval_summary_from_dashboard(),
        gemini_agent=gs.get("agent"),
        gemini_summary=gs,
        portfolio=PortfolioBrief(
            **{k: v for k, v in portfolio_data.items() if k != "_fallback"},
            fallback=bool((portfolio_data or {}).get("_fallback", False)),
        ) if portfolio_data else None,
        top_picks=[_item_to_insight(i) for i in with_gemini],
        bmv_actionable=[_item_to_insight(i) for i in actionable_raw],
        quantitative_insights=list(super_result.get("insights") or []),
        sources={
            "super_signals": "data/super_signals.json",
            "signals_bmv": "data/signals_today.json",
            "bet_policy": "data/eval/bet_policy.json",
            "eval_dashboard": "data/eval/dashboard_eval.json",
        },
    )


def export_insights_bundle(
    bundle: InsightsBundle,
    path: Path | None = None,
) -> Path:
    dest = path or INSIGHTS_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(bundle.model_dump_json(indent=2))
    return dest


def load_insights_bundle(path: Path | None = None) -> InsightsBundle | None:
    dest = path or INSIGHTS_OUT
    if not dest.exists():
        return None
    return InsightsBundle.model_validate_json(dest.read_text())
