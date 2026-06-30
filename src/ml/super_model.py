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
        · lstm_seq  : LSTMSeqPredictor → P(outperform) sobre ventanas secuenciales
  L2 — Fusión: peso de cada modelo ∝ su edge histórico (AUC − 0.5) por universo,
        O stacking LR meta-learner si ``use_stacking=True`` y supera AUC-weight.
  L3 — Moduladores: régimen (RegimeDetector HMM) × sentimiento de noticias.
  L4 — Ranking masivo cross-universo + insights (lo consume gemini_validator).

Fusión L2 — cuándo usar cada modo:
  - **Stacking LR (``use_stacking=True``, default)**: meta-LogisticRegression sobre preds
    [xs_lgbm, ensemble, heuristic, lstm_seq]; preferido post-experimentos P0 (KB-060).
  - **AUC-weight (``use_stacking=False``)**: fallback interpretable; cada modelo aporta
    según su edge medido en holdout temporal.

Diseño: cuantitativo primero. Gemini (capa 4, en gemini_validator.py) solo
valida y narra lo que este modelo decide; nunca genera la recomendación.

Uso:
    from src.ml.super_model import SuperModel
    sm = SuperModel()
    result = sm.run()          # entrena, predice, fusiona, rankea
    # result["master_ranking"] → lista de dicts ordenada por convicción

    # Con stacking meta-learner (experimental):
    sm = SuperModel(use_stacking=True)
"""
from __future__ import annotations

import logging
import warnings
from datetime import date

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from src.data import store
from src.data.universes import UNIVERSES
from src.ml.features import (
    compute_features, add_macro_features, add_cross_section_features,
    add_fundamental_features, add_news_features,
    compute_target, compute_signal_score,
    FEATURE_COLS, LONG_MOMENTUM_COLS, FUNDAMENTAL_FEATURE_COLS, NEWS_FEATURE_COLS,
)

try:
    from src.ml.intraday_features import INTRADAY_FEATURE_COLS, add_intraday_features
    _INTRADAY_AVAILABLE = True
except ImportError:
    try:
        from src.ml.intraday_features import INTRADAY_COLS as INTRADAY_FEATURE_COLS, add_intraday_features
        _INTRADAY_AVAILABLE = True
    except ImportError:
        INTRADAY_FEATURE_COLS = []  # type: ignore[misc, assignment]
        add_intraday_features = None  # type: ignore[misc, assignment]
        _INTRADAY_AVAILABLE = False

try:
    from src.ml.lstm_seq import LSTMSeqPredictor, AUC_THRESHOLD as LSTM_AUC_THRESHOLD
    _LSTM_AVAILABLE = True
except ImportError:
    LSTMSeqPredictor = None  # type: ignore[misc, assignment]
    LSTM_AUC_THRESHOLD = 0.50
    _LSTM_AVAILABLE = False

# Modelos base para fusión L2 / stacking (KB-012, KB-060)
STACK_BASE_MODELS = ("xs_lgbm", "ensemble", "heuristic", "lstm_seq")

# Conjunto extendido base (news se añade dinámicamente si hay cache)
EXTENDED_FEATURE_COLS = (
    FEATURE_COLS + LONG_MOMENTUM_COLS + FUNDAMENTAL_FEATURE_COLS + list(INTRADAY_FEATURE_COLS)
)

# Sufijo rank-normalizado (percentil cross-seccional) — sobre features extendidas
RN_COLS = [f"rn_{c}" for c in EXTENDED_FEATURE_COLS]

# Parámetros LGBM mejorados (menos regularización → más capacidad con pocos tickers)
_LGBM_BASE = dict(
    n_estimators=500, num_leaves=31, learning_rate=0.02, min_child_samples=20,
    feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, reg_lambda=3.0,
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

    def __init__(
        self,
        top_gemini: int = 10,
        verbose: bool = True,
        use_stacking: bool = True,
        include_intraday: bool = True,
    ):
        """
        Parameters
        ----------
        top_gemini   : cuántos tickers del ranking enviar a Gemini validator.
        verbose      : imprimir progreso en stdout.
        use_stacking : si True, entrena meta-LR sobre preds base y la usa cuando
                       supere AUC-weight en holdout temporal (KB-060).
        include_intraday : añade microestructura 5m→diario cuando hay parquet cache.
        """
        self.top_gemini = top_gemini
        self.verbose = verbose
        self.use_stacking = use_stacking
        self.include_intraday = include_intraday and _INTRADAY_AVAILABLE
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
        from src.ml.bet_policy import USE_NEWS_FEATURES
        if not USE_NEWS_FEATURES:
            self._news = None
            return
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

    def _extended_cols(self, available: set[str]) -> list[str]:
        """Features extendidas: técnicas + momentum + fundamentales + intraday + news."""
        base = list(EXTENDED_FEATURE_COLS)
        if self._news is not None:
            news_cols = list(NEWS_FEATURE_COLS)
            base.extend(c for c in news_cols if c not in base)
        return [c for c in base if c in available]

    @staticmethod
    def _impute_intraday_cross_section(
        frames: dict[str, pd.DataFrame],
        cols: list[str],
    ) -> None:
        """Rellena NaN intradía con mediana cross-seccional por fecha."""
        avail_cols = [c for c in cols if any(c in df.columns for df in frames.values())]
        if not avail_cols:
            return

        date_medians: dict[str, pd.Series] = {}
        for col in avail_cols:
            stacked = pd.DataFrame(
                {name: df[col] for name, df in frames.items() if col in df.columns}
            )
            date_medians[col] = stacked.median(axis=1)

        for name, df in frames.items():
            for col in avail_cols:
                if col not in df.columns:
                    continue
                med = date_medians[col].reindex(df.index)
                fallback = date_medians[col].median()
                df[col] = df[col].fillna(med).fillna(fallback if pd.notna(fallback) else 0.0)

    def _build_universe_frames(self, tickers: dict[str, str], horizon: int):
        """Carga precios del store, computa features+macro+fundamentales+intraday+news."""
        frames: dict[str, pd.DataFrame] = {}
        for name, sym in tickers.items():
            df = store.load(sym)
            if df is None or len(df) < 150:
                continue
            try:
                feat = compute_features(df)
                if self._macro:
                    feat = add_macro_features(feat, self._macro)
                feat = add_fundamental_features(feat, symbol=sym)
                if self.include_intraday and add_intraday_features is not None:
                    feat = add_intraday_features(feat, name)
                feat["ticker"] = name
                feat["fwd_ret"] = compute_target(df, horizon=horizon)
                if self._news is not None:
                    feat = add_news_features(feat, self._news, ticker_col="ticker")
                frames[name] = feat
            except Exception as e:
                logger.debug(f"{name}: {e}")
        if frames:
            frames = add_cross_section_features(frames)
            if self.include_intraday and INTRADAY_FEATURE_COLS:
                self._impute_intraday_cross_section(frames, list(INTRADAY_FEATURE_COLS))
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

        feat_cols = self._extended_cols(set(next(iter(frames.values())).columns))

        # Imputar fundamentales (yfinance/trimestral) para no perder filas
        for name in list(frames.keys()):
            df = frames[name]
            for col in FUNDAMENTAL_FEATURE_COLS:
                if col in df.columns:
                    med = df[col].median()
                    frames[name][col] = df[col].fillna(med if pd.notna(med) else 0.0)

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
        full["y_rel"] = (g["fwd_ret"].rank(pct=True) > 0.5).astype(int)
        full["y_abs"] = (full["fwd_ret"] > 0).astype(int)

        rn_avail = [f"rn_{c}" for c in feat_cols]
        full = full.dropna(subset=rn_avail + ["pct_fwd"])
        if len(full) < 200:
            return []

        cut = full.index[int(len(full) * 0.80)]
        train, valid = full[full.index < cut], full[full.index >= cut]
        if len(valid) < 30 or train["y_rel"].nunique() < 2:
            train, valid = full, full

        signals_by_model: dict[str, dict[str, float]] = {}
        auc: dict[str, float] = {}
        valid_preds: dict[str, np.ndarray] = {}
        meta_lr: LogisticRegression | None = None
        use_stack_fusion = False
        stack_auc = fusion_auc = 0.5

        # ── Modelo 1: xs_lgbm ─────────────────────────────────────────────────
        try:
            import lightgbm as lgb
            reg = lgb.LGBMRegressor(**_LGBM_BASE)
            reg.fit(train[rn_avail].values, train["pct_fwd"].values)
            p_val = reg.predict(valid[rn_avail].values)
            auc["xs_lgbm"] = self._safe_auc(valid["y_rel"].values, p_val)
            valid_preds["xs_lgbm"] = p_val
            today = self._today_rn(frames, feat_cols)
            if today is not None and not today.empty:
                preds = reg.predict(today[rn_avail].fillna(0.5).values)
                signals_by_model["xs_lgbm"] = dict(zip(today["ticker"], _minmax(preds)))
        except Exception as e:
            logger.debug(f"xs_lgbm {uname}: {e}")

        # ── Modelo 2: EnsembleModel ─────────────────────────────────────────
        try:
            from src.ml.ensemble import EnsembleModel
            ens = EnsembleModel(top_features=min(12, len(feat_cols)), calibrate=True)
            ens.fit(train, feature_cols=feat_cols, target_col="y_rel")
            p_val = ens.predict_proba(valid, feat_cols)
            auc["ensemble"] = self._safe_auc(valid["y_rel"].values, p_val)
            valid_preds["ensemble"] = p_val
            today = self._today_rows(frames, feat_cols)
            if today is not None and not today.empty:
                preds = ens.predict_proba(today, feat_cols)
                signals_by_model["ensemble"] = dict(zip(today["ticker"], preds))
        except Exception as e:
            logger.debug(f"ensemble {uname}: {e}")

        # ── Modelo 3: heurística ────────────────────────────────────────────
        try:
            hscores: dict[str, float] = {}
            h_val_raw = []
            for _, row in valid.iterrows():
                s, _ = compute_signal_score(row)
                h_val_raw.append(s)
            if h_val_raw:
                valid_preds["heuristic"] = _minmax(np.array(h_val_raw))
                auc["heuristic"] = self._safe_auc(
                    valid["y_rel"].values, valid_preds["heuristic"]
                )
            for name, df in frames.items():
                clean = df.dropna(subset=feat_cols)
                if clean.empty:
                    continue
                s, _ = compute_signal_score(clean.iloc[-1])
                hscores[name] = s
            if hscores:
                names = list(hscores.keys())
                norm = _minmax(np.array([hscores[n] for n in names]))
                signals_by_model["heuristic"] = dict(zip(names, norm))
                if "heuristic" not in auc:
                    auc["heuristic"] = 0.52
        except Exception as e:
            logger.debug(f"heuristic {uname}: {e}")

        # ── Modelo 4: lstm_seq (KB-012) ─────────────────────────────────────
        lstm_predictor = None
        if _LSTM_AVAILABLE and LSTMSeqPredictor is not None:
            try:
                lstm_predictor = LSTMSeqPredictor(sequence_length=30, epochs=12)
                lstm_predictor.fit(train, feature_cols=feat_cols, target_col="y_rel")
                if lstm_predictor.is_fitted:
                    p_val_lstm = lstm_predictor.predict_proba(valid, feat_cols)
                    mask = np.isfinite(p_val_lstm)
                    if mask.sum() >= 30:
                        auc_lstm = self._safe_auc(
                            valid["y_rel"].values[mask], p_val_lstm[mask]
                        )
                        auc["lstm_seq"] = auc_lstm
                        valid_preds["lstm_seq"] = p_val_lstm
                        today_lstm = lstm_predictor.predict_proba_today(frames, feat_cols)
                        if today_lstm:
                            signals_by_model["lstm_seq"] = today_lstm
                        if auc_lstm < LSTM_AUC_THRESHOLD:
                            logger.info(
                                f"[{uname}] lstm_seq excluido de fusión: "
                                f"AUC={auc_lstm:.3f} < {LSTM_AUC_THRESHOLD}"
                            )
                            signals_by_model.pop("lstm_seq", None)
                            valid_preds.pop("lstm_seq", None)
                            auc.pop("lstm_seq", None)
                    else:
                        logger.info(f"[{uname}] lstm_seq: pocas preds válidas en holdout")
                else:
                    logger.info(f"[{uname}] lstm_seq no fitted — excluido de fusión")
            except Exception as e:
                logger.debug(f"lstm_seq {uname}: {e}")

        # ── Modelo extra: woe_abs (producción) ──────────────────────────────
        try:
            from src.ml.ensemble import EnsembleModel
            base_feat_cols = [c for c in FEATURE_COLS if c in feat_cols]
            if base_feat_cols and train["y_abs"].nunique() > 1:
                ens_abs = EnsembleModel(top_features=min(12, len(base_feat_cols)), calibrate=True)
                ens_abs.fit(train, feature_cols=base_feat_cols, target_col="y_abs")
                p_val_abs = ens_abs.predict_proba(valid, base_feat_cols)
                auc["woe_abs"] = self._safe_auc(valid["y_abs"].values, p_val_abs)
                today = self._today_rows(frames, base_feat_cols)
                if today is not None and not today.empty:
                    preds = ens_abs.predict_proba(today, base_feat_cols)
                    signals_by_model["woe_abs"] = dict(zip(today["ticker"], preds))
        except Exception as e:
            logger.debug(f"woe_abs {uname}: {e}")

        if not signals_by_model:
            return []

        # ── Stacking meta-LR vs AUC-weight (KB-060) ──────────────────────────
        stack_models = [
            m for m in STACK_BASE_MODELS
            if m in valid_preds and m in signals_by_model
        ]
        if self.use_stacking and len(stack_models) >= 2:
            X_meta = np.column_stack([valid_preds[m] for m in stack_models])
            mask = np.all(np.isfinite(X_meta), axis=1)
            if mask.sum() >= 30 and len(np.unique(valid["y_rel"].values[mask])) >= 2:
                meta_lr = LogisticRegression(max_iter=500, random_state=42)
                meta_lr.fit(X_meta[mask], valid["y_rel"].values[mask])
                stack_auc = self._safe_auc(
                    valid["y_rel"].values[mask],
                    meta_lr.predict_proba(X_meta[mask])[:, 1],
                )
                fusion_scores = self._auc_weight_blend(
                    {m: valid_preds[m][mask] for m in stack_models}, auc, stack_models
                )
                fusion_auc = self._safe_auc(valid["y_rel"].values[mask], fusion_scores)
                use_stack_fusion = stack_auc >= fusion_auc
                self._log(
                    f"  [{uname}] stacking AUC={stack_auc:.3f} vs "
                    f"AUC-weight={fusion_auc:.3f} → "
                    f"{'stacking' if use_stack_fusion else 'AUC-weight'}"
                )

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

            base_sigs = {m: sigs[m] for m in STACK_BASE_MODELS if m in sigs}
            extra_sigs = {m: sigs[m] for m in sigs if m not in STACK_BASE_MODELS}

            if use_stack_fusion and meta_lr is not None and len(base_sigs) >= 2:
                ordered = [m for m in stack_models if m in base_sigs]
                X_t = np.array([[base_sigs[m] for m in ordered]])
                conviction = float(meta_lr.predict_proba(X_t)[0, 1])
                weights = {m: 1.0 / len(ordered) for m in ordered}
                for m, v in extra_sigs.items():
                    w = max(auc.get(m, 0.5) - 0.5, 0.0)
                    if w > 0:
                        conviction = 0.85 * conviction + 0.15 * v
                wsum = len(ordered)
            else:
                weights = {m: max(auc.get(m, 0.5) - 0.5, 0.0) for m in sigs}
                wsum = sum(weights.values())
                if wsum <= 0:
                    weights = {m: 1.0 for m in sigs}
                    wsum = len(sigs)
                conviction = sum(sigs[m] * weights[m] / wsum for m in sigs)

            stack_sigs = {**base_sigs, **extra_sigs}
            disagreement = float(np.std(list(stack_sigs.values()))) if len(stack_sigs) > 1 else 0.0
            conviction_adj = conviction * regime_factor

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
                "model_weights": {m: round(weights.get(m, 0) / max(wsum, 1), 3) for m in sigs},
                "fusion_mode": "stacking" if use_stack_fusion else "auc_weight",
                "regime": regime_info["estado"],
                "regime_factor": regime_factor,
                "news_sent": round(news_sent, 3) if news_sent is not None else None,
                "news_alerta": news_alerta,
                "horizonte_d": horizon,
            })

        for r in results:
            r["model_auc"] = {m: round(auc.get(m, 0.5), 4) for m in r["signals"]}
            if self.use_stacking:
                r["stack_auc"] = round(stack_auc, 4)
                r["fusion_auc"] = round(fusion_auc, 4)

        auc_log = {k: round(v, 3) for k, v in auc.items()}
        lstm_tag = " +lstm" if "lstm_seq" in auc else ""
        self._log(
            f"  [{uname}] {len(results)} tickers · régimen {regime_info['estado']} "
            f"(×{regime_factor}) · AUC {auc_log}{lstm_tag}"
        )
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
    def _auc_weight_blend(
        preds: dict[str, np.ndarray],
        auc: dict[str, float],
        models: list[str],
    ) -> np.ndarray:
        """Fusión AUC-weight fila a fila (para comparar vs stacking en holdout)."""
        weights = {m: max(auc.get(m, 0.5) - 0.5, 0.0) for m in models}
        wsum = sum(weights.values()) or len(models)
        if wsum <= 0:
            weights = {m: 1.0 for m in models}
            wsum = len(models)
        out = np.zeros(len(next(iter(preds.values()))))
        for m in models:
            out += preds[m] * weights[m] / wsum
        return out

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
