"""
Pipeline unificado de señales BMV — SuperModel + Gemini + Risk Engine.

Flujo (decision_protocol.yaml):
  1. SuperModel: 4 modelos base → fusión (stacking) → convicción por ticker
  2. Gemini validator: CONFIRMA / DEGRADA / VETA + noticias (top BMV)
  3. bet_policy: K=2, min convicción 0.56, paper only
  4. Risk engine: Kelly, ATR stops, correlación
  5. JSON: signals_today.json + super_signals.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.data.universes import UNIVERSES
from src.ml.bet_policy import (
    KELLY_FRAC,
    MAX_POSITION_PCT,
    MAX_SIGNALS,
    MIN_CONVICTION,
    PAPER_ONLY,
    USE_STACKING_DEFAULT,
    export_policy_json,
    filter_actionable_ranking,
    prob_thresh_for_regime,
)
from src.ml.features import compute_features
from src.ml.gemini_validator import validate_ranking
from src.ml.gemini_trader import advise_ranking
from src.ml.pipeline import market_is_riskon
from src.ml.regime import RegimeDetector
from src.ml.risk_engine import (
    Signal,
    build_signal,
    compute_correlation_matrix,
    correlation_penalty,
    portfolio_summary,
)
from src.ml.super_model import SuperModel

from src.ml.insights_bundle import build_insights_bundle, export_insights_bundle, INSIGHTS_OUT

ROOT = Path(__file__).resolve().parents[2]
BMV_SLUG = "bmv"
SUPER_OUT = ROOT / "data" / "super_signals.json"
SIGNALS_OUT = ROOT / "data" / "signals_today.json"


def tickers_map_all() -> dict[str, str]:
    """nombre_corto → símbolo yfinance (todos los universos)."""
    m: dict[str, str] = {}
    for cfg in UNIVERSES.values():
        m.update(cfg["tickers"])
    return m


def bmv_ranking(master_ranking: list[dict]) -> list[dict]:
    """Ranking BMV ordenado por convicción."""
    items = [r for r in master_ranking if r.get("universe_slug") == BMV_SLUG]
    items.sort(key=lambda x: float(x.get("conviction") or 0), reverse=True)
    return items


def gemini_size_factor(gemini: dict | None) -> float:
    """Multiplicador de tamaño según veredicto Gemini (validator o trader)."""
    if not gemini:
        return 0.75
    ver = gemini.get("veredicto", "")
    # Modo validator (legacy)
    if ver == "CONFIRMA":
        return 1.0
    if ver == "DEGRADA":
        return 0.5
    if ver == "VETA":
        return 0.0
    # Modo trader
    if ver == "APOSTAR":
        tam = (gemini.get("como_apostar") or {}).get("tamano", "HALF")
        return {"FULL": 1.0, "HALF": 0.5, "TACTICAL": 0.35, "NONE": 0.0}.get(tam, 0.5)
    if ver == "ESPERAR":
        return 0.25
    if ver == "EVITAR":
        return 0.0
    return 0.0


def compute_atr14_map(data: dict[str, pd.DataFrame]) -> dict[str, float]:
    """ATR(14) del último día por ticker."""
    out: dict[str, float] = {}
    for ticker, raw in data.items():
        try:
            feat = compute_features(raw)
            if "_atr14" in feat.columns and not feat["_atr14"].dropna().empty:
                out[ticker] = float(feat["_atr14"].dropna().iloc[-1])
            else:
                out[ticker] = float(raw["Close"].iloc[-1]) * 0.02
        except Exception:
            out[ticker] = float(raw["Close"].iloc[-1]) * 0.02
    return out


def detect_regime_hmm(macro: dict[str, pd.DataFrame]) -> dict:
    """Régimen HMM sobre NAFTRAC (compatible con dashboard legacy)."""
    naftrac = macro.get("NAFTRAC")
    sp500 = macro.get("SP500")
    if naftrac is None:
        return {"state": "unknown", "proba": {}, "is_favorable": True}

    try:
        detector = RegimeDetector(n_states=3, n_iter=200)
        detector.fit(naftrac, sp500)
        state = detector.predict_current(naftrac, sp500)
        proba = detector.state_proba(naftrac, sp500)
        return {
            "state": state,
            "proba": {k: round(v, 3) for k, v in proba.items()},
            "is_favorable": detector.is_favorable(naftrac, sp500),
            "stats": detector.regime_stats(naftrac, sp500).to_dict("records"),
        }
    except Exception as e:
        return {"state": "unknown", "proba": {}, "is_favorable": True, "error": str(e)}


def run_super_pipeline(
    *,
    top_gemini_global: int = 10,
    top_gemini_bmv: int = 10,
    use_gemini: bool = True,
    use_stacking: bool | None = None,
    verbose: bool = True,
    agent_role: str = "trader",
    skip_lstm: bool = False,
) -> dict:
    """
    Capas 1–4: SuperModel cross-universo + Gemini (global + BMV dedicado).
    """
    stacking = USE_STACKING_DEFAULT if use_stacking is None else use_stacking
    export_policy_json()

    sm = SuperModel(
        top_gemini=top_gemini_global,
        use_stacking=stacking,
        verbose=verbose,
        skip_lstm=skip_lstm,
    )
    result = sm.run()

    if use_gemini:
        advise_fn = advise_ranking if agent_role == "trader" else validate_ranking
        result = advise_fn(
            result,
            tickers_map=tickers_map_all(),
            top_n=top_gemini_global,
        )
        # Validación dedicada BMV (el top global puede ser USA/crypto)
        bmv_items = bmv_ranking(result["master_ranking"])
        pending = [it for it in bmv_items[:top_gemini_bmv] if "gemini" not in it]
        if pending:
            sub = {"master_ranking": pending, "top_gemini": len(pending),
                   "model_registry": result.get("model_registry"),
                   "universe_metrics": result.get("universe_metrics")}
            advise_fn(sub, tickers_map=tickers_map_all(), top_n=len(pending))
            by_ticker = {it["ticker"]: it.get("gemini") for it in pending if "gemini" in it}
            for r in result["master_ranking"]:
                if r["ticker"] in by_ticker and by_ticker[r["ticker"]]:
                    r["gemini"] = by_ticker[r["ticker"]]
    else:
        result["gemini_summary"] = {"modo": "skip"}

    from src.ml.gemini_trader import advise_portfolio, _fallback_portfolio
    if use_gemini and not result.get("portfolio_brief"):
        result["portfolio_brief"] = advise_portfolio(
            result, top_n=min(top_gemini_global, 10),
        )
    elif not result.get("portfolio_brief"):
        result["portfolio_brief"] = _fallback_portfolio(
            result, top_n=min(top_gemini_global, 10),
        )

    result["bet_policy"] = {
        "paper_only": PAPER_ONLY,
        "max_signals": MAX_SIGNALS,
        "min_conviction": MIN_CONVICTION,
        "use_stacking": stacking,
    }
    result["actionable_bets_bmv"] = filter_actionable_ranking(
        bmv_ranking(result["master_ranking"]),
    )
    result["actionable_bets"] = filter_actionable_ranking(
        result["master_ranking"],
    )
    bundle = build_insights_bundle(
        result,
        portfolio=result.get("portfolio_brief"),
    )
    export_insights_bundle(bundle)
    result["insights_bundle_path"] = str(INSIGHTS_OUT)
    return result


def apply_super_risk_engine(
    actionable: list[dict],
    data: dict[str, pd.DataFrame],
    macro: dict[str, pd.DataFrame],
    regime: dict,
    capital: float,
    *,
    atr_map: dict[str, float] | None = None,
) -> tuple[list[Signal], dict, list[dict], pd.DataFrame, list[dict]]:
    """
    Construye señales finales desde items del SuperModel ya filtrados.

    Returns
    -------
    signals, summary, all_bmv_candidates, corr_matrix, enriched_items
    """
    thresh = prob_thresh_for_regime(regime.get("state"))
    atr_map = atr_map or compute_atr14_map(data)

    returns_dict = {
        t: data[t]["Close"].pct_change()
        for t in data
        if t in data and "Close" in data[t].columns
    }
    corr_matrix = compute_correlation_matrix(returns_dict, window=63)

    if not market_is_riskon(macro.get("NAFTRAC")):
        bmv_all = bmv_ranking(actionable)  # may be empty; build from caller
        return [], portfolio_summary([], capital), [], corr_matrix, []

    signals: list[Signal] = []
    selected: list[str] = []
    enriched: list[dict] = []

    for item in actionable:
        if len(signals) >= MAX_SIGNALS:
            break

        ticker = item["ticker"]
        if ticker not in data:
            continue

        conv = float(item.get("conviction") or 0)
        if conv < thresh:
            continue

        g = item.get("gemini") or {}
        g_factor = gemini_size_factor(g)
        if g_factor <= 0:
            continue

        price = float(item.get("precio") or data[ticker]["Close"].iloc[-1])
        atr = atr_map.get(ticker, price * 0.02)
        model_feats = {
            k: round(float(v), 4)
            for k, v in (item.get("signals") or {}).items()
        }
        model_feats["conviction"] = conv
        model_feats["disagreement"] = item.get("disagreement")

        corr_f = correlation_penalty(ticker, corr_matrix, selected) * g_factor
        signal = build_signal(
            ticker=ticker,
            price=price,
            atr=atr,
            p_up=min(conv, 0.99),
            capital_mxn=capital,
            corr_factor=corr_f,
            features=model_feats,
            kelly_frac=KELLY_FRAC,
            max_position=MAX_POSITION_PCT,
        )
        if signal is None:
            continue

        reason_parts = [signal.reason] if signal.reason else []
        if g.get("veredicto"):
            reason_parts.append(f"Gemini {g['veredicto']}")
        if item.get("news_sent") is not None:
            reason_parts.append(f"news_sent {item['news_sent']:+.2f}")
        signal.reason = " · ".join(p for p in reason_parts if p)

        signals.append(signal)
        selected.append(ticker)
        enriched.append({**item, "risk_signal": True})

    summary = portfolio_summary(signals, capital)
    return signals, summary, [], corr_matrix, enriched


def signal_to_dict(s: Signal) -> dict:
    return {
        "ticker": s.ticker,
        "price": s.price,
        "atr": s.atr,
        "p_up": s.p_up,
        "entry": s.entry,
        "stop": s.stop,
        "target_1": s.target_1,
        "target_2": s.target_2,
        "kelly_f": s.kelly_f,
        "pct_capital": s.pct_capital,
        "shares": s.shares,
        "capital_mxn": s.capital_mxn,
        "risk_pct": s.risk_pct,
        "rr_ratio": s.rr_ratio,
        "edge": s.edge,
        "features": s.features,
        "reason": s.reason,
    }


def build_signals_output(
    *,
    signals: list[Signal],
    summary: dict,
    super_result: dict,
    enriched_items: list[dict],
    all_bmv: list[dict],
    corr_matrix: pd.DataFrame,
    capital: float,
    regime: dict,
    context: dict | None = None,
) -> dict:
    """Payload JSON para signals_today.json."""
    thresh = prob_thresh_for_regime(regime.get("state"))
    sigs_out = [signal_to_dict(s) for s in signals]

    # Enriquecer con capa Gemini + preds por modelo
    by_ticker = {it["ticker"]: it for it in enriched_items}
    for sig in sigs_out:
        src = by_ticker.get(sig["ticker"], {})
        sig["model_signals"] = src.get("signals", {})
        sig["model_auc"] = src.get("model_auc", {})
        sig["fusion_mode"] = src.get("fusion_mode")
        sig["disagreement"] = src.get("disagreement")
        sig["conviction"] = src.get("conviction")
        sig["rank_global"] = src.get("rank_global")
        sig["gemini"] = src.get("gemini", {})
        sig["news_sent"] = src.get("news_sent")
        sig["news_alerta"] = src.get("news_alerta", False)

    tickers_in = [s["ticker"] for s in sigs_out]
    corr_top: dict[str, dict] = {}
    for t in tickers_in:
        if t in corr_matrix.index:
            row = corr_matrix.loc[t].drop(labels=[t], errors="ignore")
            corr_top[t] = {k: round(float(v), 3) for k, v in row.items()}

    candidates = []
    for item in all_bmv[:25]:
        candidates.append({
            "ticker": item["ticker"],
            "price": item.get("precio"),
            "conviction": item.get("conviction"),
            "p_up": item.get("conviction"),
            "disagreement": item.get("disagreement"),
            "signals": item.get("signals"),
            "gemini": item.get("gemini"),
            "rank_global": item.get("rank_global"),
            "news_sent": item.get("news_sent"),
        })

    gs = super_result.get("gemini_summary", {})
    return {
        "meta": {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "capital": capital,
            "threshold": thresh,
            "threshold_base": MIN_CONVICTION,
            "max_signals": MAX_SIGNALS,
            "paper_only": PAPER_ONLY,
            "horizon": 5,
            "model": "SuperModel (4 base + stacking) + Gemini validator",
            "pipeline": "signal_pipeline.run_super_pipeline",
            "use_stacking": super_result.get("bet_policy", {}).get("use_stacking"),
            "gemini_summary": gs,
        },
        "regime": regime,
        "signals": sigs_out,
        "summary": summary,
        "all_candidates": candidates,
        "correlations": corr_top,
        "market_context": context or {},
        "super_model": {
            "n_tickers": super_result.get("n_tickers"),
            "actionable_bets": [
                {
                    "ticker": x["ticker"],
                    "conviction": x.get("conviction"),
                    "gemini": x.get("gemini", {}).get("veredicto"),
                }
                for x in super_result.get("actionable_bets_bmv", [])
            ],
            "insights": super_result.get("insights", [])[:5],
        },
    }


def generate_bmv_signals(
    data: dict[str, pd.DataFrame],
    macro: dict[str, pd.DataFrame],
    capital: float,
    *,
    use_gemini: bool = True,
    use_stacking: bool | None = None,
    top_gemini_bmv: int = 10,
    context: dict | None = None,
    write_super: bool = True,
) -> tuple[dict, Path]:
    """
    Pipeline completo BMV → guarda signals_today.json (+ super_signals.json).

    Returns
    -------
    (output_dict, path_to_signals_today)
    """
    regime = detect_regime_hmm(macro)
    regime["market_riskon"] = market_is_riskon(macro.get("NAFTRAC"))

    super_result = run_super_pipeline(
        top_gemini_global=10,
        top_gemini_bmv=top_gemini_bmv,
        use_gemini=use_gemini,
        use_stacking=use_stacking,
        verbose=True,
    )
    super_result["generated_at"] = datetime.now().isoformat()

    all_bmv = bmv_ranking(super_result["master_ranking"])
    actionable = super_result.get("actionable_bets_bmv") or filter_actionable_ranking(all_bmv)

    atr_map = compute_atr14_map(data)
    signals, summary, _, corr_matrix, enriched = apply_super_risk_engine(
        actionable,
        data,
        macro,
        regime,
        capital,
        atr_map=atr_map,
    )

    # Si risk-off, igual exportar candidatos BMV para el dashboard
    if not regime.get("market_riskon"):
        summary = portfolio_summary([], capital)

    output = build_signals_output(
        signals=signals,
        summary=summary,
        super_result=super_result,
        enriched_items=enriched,
        all_bmv=all_bmv,
        corr_matrix=corr_matrix,
        capital=capital,
        regime=regime,
        context=context,
    )

    SIGNALS_OUT.parent.mkdir(parents=True, exist_ok=True)
    SIGNALS_OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    if write_super:
        SUPER_OUT.write_text(json.dumps(super_result, indent=2, ensure_ascii=False))
        bundle = build_insights_bundle(
            super_result,
            bmv_actionable=actionable,
            portfolio=super_result.get("portfolio_brief"),
        )
        export_insights_bundle(bundle)

    return output, SIGNALS_OUT
