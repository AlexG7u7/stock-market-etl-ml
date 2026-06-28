"""
Detector de régimen de mercado con Hidden Markov Model (HMM).

Arquitectura:
  - 3 estados ocultos: BULL (0), LATERAL (1), BEAR (2)
  - Features observables: retorno IPC 5d, volatilidad realizada 20d,
    amplitud de rango (High-Low/Close), retorno S&P500 5d
  - Modelo Gaussian HMM con covarianzas diagonales

Uso:
    from src.ml.regime import RegimeDetector

    detector = RegimeDetector()
    detector.fit(naftrac_df, sp500_df)          # entrena sobre histórico
    state = detector.predict_current(naftrac_df) # 'bull' | 'lateral' | 'bear'
    proba = detector.state_proba(naftrac_df)     # dict con P(bull), P(lateral), P(bear)

    # Para señales: solo emitir si P(bull) > 0.5
    if detector.is_favorable(naftrac_df):
        # proceder con señales del ensemble
        ...
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Estado 0 = BULL, 1 = LATERAL, 2 = BEAR (se determina post-fit por retorno medio)
_STATE_LABELS = ["bull", "lateral", "bear"]


def _build_features(naftrac: pd.DataFrame, sp500: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Construye features para el HMM a partir de series diarias del IPC (NAFTRAC)
    y opcionalmente el S&P500.

    Returns DataFrame con columnas: ret5, vol20, range_pct, [sp_ret5]
    """
    close = naftrac["Close"]
    high  = naftrac["High"]  if "High"  in naftrac.columns else close
    low   = naftrac["Low"]   if "Low"   in naftrac.columns else close

    ret5    = close.pct_change(5).fillna(0)
    ret1    = close.pct_change(1).fillna(0)
    vol20   = ret1.rolling(20).std().fillna(ret1.std())  # volatilidad realizada
    rng_pct = ((high - low) / close).fillna(0)           # amplitud diaria

    feats = pd.DataFrame({
        "ret5":    ret5,
        "vol20":   vol20,
        "rng_pct": rng_pct,
    }, index=naftrac.index)

    if sp500 is not None:
        sp_ret5 = sp500["Close"].pct_change(5).reindex(naftrac.index, method="ffill").fillna(0)
        feats["sp_ret5"] = sp_ret5

    return feats.dropna()


def _label_states(model, X: np.ndarray, states: np.ndarray) -> dict[int, str]:
    """
    Asigna etiquetas semánticas (bull/lateral/bear) a los estados del HMM
    según el retorno medio de cada estado: el más alto = bull, más bajo = bear.
    """
    # Retorno medio (primera feature = ret5) por estado
    mean_rets = {}
    for s in range(model.n_components):
        mask = states == s
        if mask.sum() > 0:
            mean_rets[s] = X[mask, 0].mean()
        else:
            mean_rets[s] = 0.0

    sorted_states = sorted(mean_rets.keys(), key=lambda s: mean_rets[s], reverse=True)
    label_map = {}
    for rank, state_id in enumerate(sorted_states):
        if rank == 0:
            label_map[state_id] = "bull"
        elif rank == len(sorted_states) - 1:
            label_map[state_id] = "bear"
        else:
            label_map[state_id] = "lateral"
    return label_map


class RegimeDetector:
    """
    HMM Gaussian de 3 estados para detección de régimen del mercado mexicano.
    Se entrena sobre el histórico del IPC (NAFTRAC) y opcionalmente el S&P500.
    """

    def __init__(self, n_states: int = 3, n_iter: int = 200):
        self.n_states    = n_states
        self.n_iter      = n_iter
        self._model      = None
        self._label_map  = {}   # int → 'bull'|'lateral'|'bear'
        self._feats_hist: pd.DataFrame | None = None

    # ── Entrenamiento ─────────────────────────────────────────────────────────

    def fit(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
        train_cutoff: str | None     = None,
    ) -> "RegimeDetector":
        """
        Entrena el HMM sobre datos históricos del IPC.

        Args:
            naftrac:       DataFrame OHLCV del NAFTRAC / IPC.
            sp500:         DataFrame OHLCV del S&P500 (opcional, mejora el modelo).
            train_cutoff:  Si se especifica, entrena solo hasta esa fecha (YYYY-MM-DD).
        """
        from hmmlearn.hmm import GaussianHMM

        feats = _build_features(naftrac, sp500)
        if train_cutoff:
            feats = feats.loc[:train_cutoff]

        self._feats_hist = feats  # guardar para predict

        X = feats.values.astype(np.float64)
        lengths = [len(X)]

        model = GaussianHMM(
            n_components   = self.n_states,
            covariance_type= "diag",
            n_iter         = self.n_iter,
            random_state   = 42,
            tol            = 1e-4,
        )
        model.fit(X, lengths)
        self._model = model

        # Decodificar secuencia histórica para etiquetar estados
        states = model.predict(X)
        self._label_map = _label_states(model, X, states)

        return self

    # ── Predicción ────────────────────────────────────────────────────────────

    def _get_feats_for(self, naftrac: pd.DataFrame, sp500: pd.DataFrame | None = None) -> np.ndarray:
        feats = _build_features(naftrac, sp500)
        # Alinear columnas con las del entrenamiento
        cols  = self._feats_hist.columns.tolist()
        feats = feats.reindex(columns=cols, fill_value=0)
        return feats.values.astype(np.float64)

    def predict_series(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
    ) -> pd.Series:
        """
        Devuelve una Serie de etiquetas ('bull'|'lateral'|'bear') para cada fecha.
        """
        if self._model is None:
            raise RuntimeError("Debes llamar fit() antes de predict_series()")
        X      = self._get_feats_for(naftrac, sp500)
        feats  = _build_features(naftrac, sp500)
        states = self._model.predict(X)
        labels = pd.Series(
            [self._label_map.get(s, "lateral") for s in states],
            index=feats.index,
            name="regime",
        )
        return labels

    def predict_current(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
    ) -> str:
        """Devuelve el régimen del último día disponible."""
        return self.predict_series(naftrac, sp500).iloc[-1]

    def state_proba(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
        date:    str | None          = None,
    ) -> dict[str, float]:
        """
        Probabilidad suavizada (forward-backward) de cada estado para una fecha.
        Si date=None, usa el último día disponible.
        """
        if self._model is None:
            raise RuntimeError("Debes llamar fit() antes de state_proba()")

        X     = self._get_feats_for(naftrac, sp500)
        feats = _build_features(naftrac, sp500)

        # Probabilidades posteriores (n_samples × n_states)
        log_proba = self._model.predict_proba(X)  # (N, n_states)

        if date is not None:
            try:
                idx = feats.index.get_loc(date)
            except KeyError:
                idx = -1
        else:
            idx = -1

        proba_row = log_proba[idx]
        return {
            self._label_map.get(s, f"state_{s}"): float(proba_row[s])
            for s in range(self.n_states)
        }

    def is_favorable(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
        min_bull_proba: float        = 0.45,
    ) -> bool:
        """
        True si el régimen actual es favorable para señales de compra.
        Condición: P(bull) + 0.5*P(lateral) > min_bull_proba
        """
        proba = self.state_proba(naftrac, sp500)
        score = proba.get("bull", 0) + 0.5 * proba.get("lateral", 0)
        return score >= min_bull_proba

    def regime_stats(
        self,
        naftrac: pd.DataFrame,
        sp500:   pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Tabla resumen: frecuencia y retorno medio de cada régimen en el histórico.
        """
        feats   = _build_features(naftrac, sp500)
        labels  = self.predict_series(naftrac, sp500)
        ret5    = naftrac["Close"].pct_change(5).reindex(labels.index)

        rows = []
        for regime in ["bull", "lateral", "bear"]:
            mask    = labels == regime
            n       = mask.sum()
            ret_avg = ret5[mask].mean() * 100 if n > 0 else 0
            ret_std = ret5[mask].std()  * 100 if n > 0 else 0
            rows.append({
                "regime":    regime,
                "n_days":    int(n),
                "pct_time":  round(n / len(labels) * 100, 1),
                "ret5_mean": round(ret_avg, 2),
                "ret5_std":  round(ret_std, 2),
            })
        return pd.DataFrame(rows)
