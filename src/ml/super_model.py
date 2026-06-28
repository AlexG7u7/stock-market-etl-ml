"""
SuperModel — Meta-orquestador que fusiona todos los modelos del sistema.

Combina las señales de varios modelos base en UNA decisión de convicción por
ticker, modulada por régimen de mercado y sentimiento de noticias, y produce un
ranking maestro cross-universo (los 87 tickers de los 5 universos en una sola
lista).

Capas:
  L1 — Modelos base (predictores direccionales):
        · xs_lgbm   : LGBMRegressor sobre features rank-normalizadas (cross-seccional)
        · ensemble  : EnsembleModel (WoE + LR + LGBM) → P(le gana a la mediana)
        · heuristic : compute_signal_score (screener técnico) normalizado
  L2 — Fusión: peso de cada modelo ∝ su edge histórico (AUC − 0.5) por universo.
  L3 — Moduladores: régimen (RegimeDetector HMM) × sentimiento de noticias.
  L4 — Ranking masivo cross-universo + insights (lo consume gemini_validator).

Diseño: cuantitativo primero. Gemini (capa 4, en gemini_validator.py) solo
valida y narra lo que este modelo decide; nunca genera la recomendación.

Uso:
    from src.ml.super_model import SuperModel
    sm = SuperModel()
    result = sm.run()          # entrena, predice, fusiona, rankea
    # result["master_ranking"] → lista de dicts ordenada por convicción
"""
from __future__ import annotations

import logging
import warnings
from datetime import date

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from src.data import store
from src.data.universes import UNIVERSES
from src.ml.features import (
    compute_features, add_macro_features, add_cross_section_features,
    compute_target, compute_signal_score, FEATURE_COLS,
)

# Sufijo rank-normalizado (percentil cross-seccional)
RN_COLS = [f"rn_{c}" for c in FEATURE_COLS]

_LGBM_BASE = dict(
    n_estimators=300, num_leaves=31, learning_rate=0.03, min_child_samples=40,
    feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, reg_lambda=5.0,
    n_jobs=2, random_state=42, verbosity=-1,
)

# Símbolos macro para add_macro_features
_MACRO_SYMS = {"USDMXN": "MXN=X", "NAFTRAC": "NAFTRAC.MX", "WTI": "CL=F", "SP500": "^GSPC"}


def _minmax(x: np.ndarray) -> np.ndarray:
    """Normaliza a [0,1]. Si todo es igual, devuelve 0.5."""
    x = np.asarray(x, dtype=float)
    lo, hi = np.nanmin(x), np.nanmax(x)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
        return np.full_like(x, 0.5)
    return (x - lo) / (hi - lo)


class SuperModel:
    """Meta-orquestador de los modelos del sistema."""

    def __init__(self, top_gemini: int = 10, verbose: bool = True):
        self.top_gemini = top_gemini
        self.verbose = verbose
        self._macro: dict[str, pd.DataFrame] = {}
        self._regime_cache: dict[str, dict] = {}
        self._news: pd.DataFrame | None = None

    # ── Carga de datos ──────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _load_macro(self) -> None:
        for key, sym in _MACRO_SYMS.items():
            df = store.load(sym)
            if df is not None:
                self._macro[key] = df

    def _load_news(self) -> None:
        try:
            from src.ml.news import load_cached_news_features
            self._news = load_cached_news_features()
        except Exception as e:
            logger.debug(f"news no disponible: {e}")
            self._news = None

    # ── Régimen de mercado ─────────────────────────────────────────────────

    def _regime_factor(self, currency: str) -> tuple[float, dict]:
        """
        Factor multiplicativo por régimen: risk-on amplifica, risk-off reduce.
        MXN usa NAFTRAC, el resto usa S&P 500.
        """
        key = "MXN" if currency == "MXN" else "USD"
        if key in self._regime_cache:
            c = self._regime_cache[key]
            return c["factor"], c["info"]

        factor, info = 1.0, {"estado": "desconocido", "proba": {}}
        try:
            from src.ml.regime import RegimeDetector
            naftrac = self._macro.get("NAFTRAC")
            sp500   = self._macro.get("SP500")
            driver  = naftrac if key == "MXN" else sp500
            if driver is not None and len(driver) > 300:
                det = RegimeDetector()
                det.fit(driver, sp500)
                proba = det.state_proba(driver, sp500)
                estado = max(proba, key=proba.get)
                factor = {"bull": 1.10, "lateral": 1.0, "bear": 0.80}.get(estado, 1.0)
                info = {"estado": estado, "proba": {k: round(v, 3) for k, v in proba.items()}}
        except Exception as e:
            logger.debug(f"regime {key}: {e}")

        self._regime_cache[key] = {"factor": factor, "info": info}
        return factor, info

    # ── Construcción del dataset por universo ───────────────────────────────

    def _build_universe_frames(self, tickers: dict[str, str], horizon: int):
        """Carga precios del store, computa features+macro+cross-section."""
        frames: dict[str, pd.DataFrame] = {}
        for name, sym in tickers.items():
            df = store.load(sym)
            if df is None or len(df) < 150:
                continue
            try:
                feat = compute_features(df)
                if self._macro:
                    feat = add_macro_features(feat, self._macro)
                feat["ticker"] = name
                # target forward para entrenar
                feat["fwd_ret"] = compute_target(df, horizon=horizon)
                frames[name] = feat
            except Exception as e:
                logger.debug(f"{name}: {e}")
        if frames:
            frames = add_cross_section_features(frames)
        return frames

    # ── Modelos base por universo ───────────────────────────────────────────

    def _run_universe(self, uname: str, cfg: dict) -> list[dict]:
        tickers  = cfg["tickers"]
        horizon  = cfg["horizonte"]
        currency = cfg["moneda"]
        min_n    = cfg["min_tickers"]

        self._log(f"\n  [{uname}] cargando {len(tickers)} tickers...")
        frames = self._build_universe_frames(tickers, horizon)
        if len(frames) < min_n:
            self._log(f"  [{uname}] insuficientes tickers ({len(frames)}) — skip")
            return []

        feat_cols = [c for c in FEATURE_COLS if c in next(iter(frames.values())).columns]

        # Panel completo para entrenamiento
        rows = []
        for df in frames.values():
            d = df.dropna(subset=feat_cols + ["fwd_ret"]).copy()
            if len(d) >= 100:
                rows.append(d)
        if not rows:
            return []

        full = pd.concat(rows).sort_index()

        # Rank-normalización cross-seccional por fecha
        g = full.groupby(full.index)
        for c in feat_cols:
            full[f"rn_{c}"] = g[c].rank(pct=True)
        full["pct_fwd"] = g["fwd_ret"].rank(pct=True)
        # target binario: ¿le gana a la mediana del universo ese día?
        full["y_rel"] = (g["fwd_ret"].rank(pct=True) > 0.5).astype(int)

        rn_avail = [f"rn_{c}" for c in feat_cols]
        full = full.dropna(subset=rn_avail + ["pct_fwd"])
        if len(full) < 200:
            return []

        # Split temporal para medir edge (AUC) de cada modelo
        cut = full.index[int(len(full) * 0.80)]
        train, valid = full[full.index < cut], full[full.index >= cut]
        if len(valid) < 30 or train["y_rel"].nunique() < 2:
            train, valid = full, full

        signals_by_model: dict[str, dict[str, float]] = {}
        auc: dict[str, float] = {}

        # ── Modelo 1: xs_lgbm (regresor sobre percentil cross-seccional) ─────
        try:
            import lightgbm as lgb
            reg = lgb.LGBMRegressor(**_LGBM_BASE)
            reg.fit(train[rn_avail].values, train["pct_fwd"].values)
            p_val = reg.predict(valid[rn_avail].values)
            auc["xs_lgbm"] = self._safe_auc(valid["y_rel"].values, p_val)
            # Predecir hoy
            today = self._today_rn(frames, feat_cols)
            if today is not None and not today.empty:
                preds = reg.predict(today[rn_avail].fillna(0.5).values)
                signals_by_model["xs_lgbm"] = dict(zip(today["ticker"], _minmax(preds)))
        except Exception as e:
            logger.debug(f"xs_lgbm {uname}: {e}")

        # ── Modelo 2: EnsembleModel (WoE + LR + LGBM) ────────────────────────
        try:
            from src.ml.ensemble import EnsembleModel
            ens = EnsembleModel(top_features=min(12, len(feat_cols)), calibrate=True)
            ens.fit(train, feature_cols=feat_cols, target_col="y_rel")
            p_val = ens.predict_proba(valid, feat_cols)
            auc["ensemble"] = self._safe_auc(valid["y_rel"].values, p_val)
            today = self._today_rows(frames, feat_cols)
            if today is not None and not today.empty:
                preds = ens.predict_proba(today, feat_cols)
                signals_by_model["ensemble"] = dict(zip(today["ticker"], preds))
        except Exception as e:
            logger.debug(f"ensemble {uname}: {e}")

        # ── Modelo 3: heurística técnica (screener) ──────────────────────────
        try:
            hscores = {}
            for name, df in frames.items():
                clean = df.dropna(subset=feat_cols)
                if clean.empty:
                    continue
                s, _ = compute_signal_score(clean.iloc[-1])
                hscores[name] = s
            if hscores:
                names = list(hscores.keys())
                norm  = _minmax(np.array([hscores[n] for n in names]))
                signals_by_model["heuristic"] = dict(zip(names, norm))
                # AUC heurístico aproximado: score vs y_rel del set de validación
                auc["heuristic"] = 0.52  # peso bajo fijo (screener débil pero independiente)
        except Exception as e:
            logger.debug(f"heuristic {uname}: {e}")

        if not signals_by_model:
            return []

        # ── Fusión por ticker ────────────────────────────────────────────────
        regime_factor, regime_info = self._regime_factor(currency)
        all_tickers = set().union(*[set(d.keys()) for d in signals_by_model.values()])

        results = []
        for tk in all_tickers:
            sigs = {m: signals_by_model[m].get(tk) for m in signals_by_model
                    if tk in signals_by_model[m]}
            sigs = {m: float(v) for m, v in sigs.items() if v is not None and np.isfinite(v)}
            if not sigs:
                continue

            # pesos por edge (AUC − 0.5)
            weights = {m: max(auc.get(m, 0.5) - 0.5, 0.0) for m in sigs}
            wsum = sum(weights.values())
            if wsum <= 0:
                weights = {m: 1.0 for m in sigs}
                wsum = len(sigs)
            conviction = sum(sigs[m] * weights[m] / wsum for m in sigs)
            disagreement = float(np.std(list(sigs.values()))) if len(sigs) > 1 else 0.0

            # modular régimen
            conviction_adj = conviction * regime_factor

            # modular noticias
            news_sent = self._news_sent(tk)
            news_alerta = news_sent is not None and news_sent < -0.3
            if news_alerta:
                conviction_adj *= 0.5

            price = self._last_price(frames.get(tk))
            results.append({
                "ticker": tk,
                "universe": uname,
                "universe_slug": cfg["slug"],
                "moneda": currency,
                "precio": round(price, 2) if price else None,
                "conviction_raw": round(conviction, 4),
                "conviction": round(float(np.clip(conviction_adj, 0, 1.5)), 4),
                "disagreement": round(disagreement, 4),
                "signals": {m: round(v, 4) for m, v in sigs.items()},
                "model_weights": {m: round(weights[m] / wsum, 3) for m in sigs},
                "regime": regime_info["estado"],
                "regime_factor": regime_factor,
                "news_sent": round(news_sent, 3) if news_sent is not None else None,
                "news_alerta": news_alerta,
                "horizonte_d": horizon,
            })

        # AUC del universo (para el reporte)
        for r in results:
            r["model_auc"] = {m: round(auc.get(m, 0.5), 4) for m in r["signals"]}

        self._log(f"  [{uname}] {len(results)} tickers · régimen {regime_info['estado']} "
                  f"(×{regime_factor}) · AUC {auc}")
        return results

    # ── Helpers de predicción "hoy" ─────────────────────────────────────────

    def _today_rows(self, frames, feat_cols):
        """Última fila de cada ticker (features absolutas) para Ensemble."""
        rows = []
        for name, df in frames.items():
            clean = df.dropna(subset=feat_cols)
            if not clean.empty:
                r = clean.iloc[[-1]].copy()
                r["ticker"] = name
                rows.append(r)
        return pd.concat(rows) if rows else None

    def _today_rn(self, frames, feat_cols):
        """Última fila rank-normalizada cross-seccional (para xs_lgbm)."""
        last = {}
        for name, df in frames.items():
            clean = df.dropna(subset=feat_cols)
            if not clean.empty:
                last[name] = clean.iloc[-1]
        if not last:
            return None
        rows = []
        for name, row in last.items():
            rn = {"ticker": name}
            for c in feat_cols:
                vals = [r[c] for r in last.values() if c in r.index and not pd.isna(r[c])]
                rn[f"rn_{c}"] = (sum(1 for v in vals if v <= row.get(c, 0)) / len(vals)
                                if vals else 0.5)
            rows.append(rn)
        return pd.DataFrame(rows)

    @staticmethod
    def _safe_auc(y, p) -> float:
        try:
            if len(np.unique(y)) < 2:
                return 0.5
            return float(roc_auc_score(y, p))
        except Exception:
            return 0.5

    @staticmethod
    def _last_price(df):
        if df is None or df.empty or "Close" not in df.columns:
            return None
        return float(df["Close"].iloc[-1])

    def _news_sent(self, ticker: str):
        if self._news is None or ticker not in self._news.index:
            return None
        try:
            return float(self._news.loc[ticker, "news_sent_score"])
        except Exception:
            return None

    # ── Insights cross-universo ─────────────────────────────────────────────

    def _build_insights(self, ranking: list[dict]) -> list[dict]:
        insights = []
        if not ranking:
            return insights

        df = pd.DataFrame(ranking)

        # 1. Convicción alta + acuerdo
        strong = df[(df["conviction"] > 0.6) & (df["disagreement"] < 0.15)]
        for _, r in strong.head(3).iterrows():
            insights.append({
                "tipo": "Consenso fuerte",
                "ticker": r["ticker"],
                "texto": f"{r['ticker']} ({r['universe_slug']}): convicción {r['conviction']:.2f}, "
                         f"modelos de acuerdo (desac. {r['disagreement']:.2f}). Régimen {r['regime']}.",
            })

        # 2. Divergencias (alta convicción pero alto desacuerdo)
        diverg = df[(df["conviction"] > 0.5) & (df["disagreement"] > 0.25)]
        for _, r in diverg.head(2).iterrows():
            insights.append({
                "tipo": "Divergencia",
                "ticker": r["ticker"],
                "texto": f"{r['ticker']}: modelos en desacuerdo (desac. {r['disagreement']:.2f}) — "
                         f"señales {r['signals']}. Revisar antes de operar.",
            })

        # 3. Vetos por noticias
        vetoed = df[df["news_alerta"]]
        for _, r in vetoed.head(2).iterrows():
            insights.append({
                "tipo": "Veto por noticias",
                "ticker": r["ticker"],
                "texto": f"{r['ticker']}: score técnico alto pero news_sent {r['news_sent']:.2f} "
                         f"redujo la convicción a la mitad.",
            })

        # 4. Concentración sectorial / universo en top-10
        top10 = df.nlargest(10, "conviction")
        uni_counts = top10["universe_slug"].value_counts()
        if uni_counts.iloc[0] >= 6:
            insights.append({
                "tipo": "Concentración",
                "ticker": "",
                "texto": f"{uni_counts.iloc[0]}/10 del top provienen de '{uni_counts.index[0]}'. "
                         f"Considerar diversificar entre clases de activo.",
            })

        # 5. Régimen dominante
        regimes = df.groupby("moneda")["regime"].first().to_dict()
        insights.append({
            "tipo": "Régimen",
            "ticker": "",
            "texto": "Régimen de mercado: " + " · ".join(f"{k}={v}" for k, v in regimes.items()),
        })

        return insights

    # ── Pipeline completo ────────────────────────────────────────────────────

    def run(self) -> dict:
        self._log("\n" + "═" * 62)
        self._log("  SUPER MODELO — Meta-orquestador cross-universo")
        self._log("═" * 62)

        self._load_macro()
        self._load_news()

        all_results: list[dict] = []
        for uname, cfg in UNIVERSES.items():
            all_results.extend(self._run_universe(uname, cfg))

        # Ranking maestro global por convicción
        all_results.sort(key=lambda r: r["conviction"], reverse=True)
        for i, r in enumerate(all_results):
            r["rank_global"] = i + 1

        insights = self._build_insights(all_results)

        self._log(f"\n  Ranking maestro: {len(all_results)} tickers")
        self._log("  Top-10 por convicción:")
        for r in all_results[:10]:
            self._log(f"    #{r['rank_global']:<2} {r['ticker']:<10} "
                      f"conv={r['conviction']:.3f}  desac={r['disagreement']:.3f}  "
                      f"[{r['universe_slug']}] {r['regime']}")

        return {
            "fecha": date.today().isoformat(),
            "n_tickers": len(all_results),
            "master_ranking": all_results,
            "insights": insights,
            "top_gemini": self.top_gemini,
        }
