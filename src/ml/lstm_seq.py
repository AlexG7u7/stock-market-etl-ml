"""
Wrapper de producción para LSTM secuencial — clasificación P(up 5d).

Construye secuencias sliding-window por ticker y entrena un MLS-LSTM
multi-capa (KB-010/011) sobre features tabulares.

Uso:
    from src.ml.lstm_seq import LSTMSeqPredictor

    pred = LSTMSeqPredictor()
    pred.fit(panel_df, feature_cols=FEATURE_COLS, target_col="target_up")
    p = pred.predict_proba(panel_df, feature_cols)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.ml.features import compute_target
from src.ml.shared.models.lstm_model import LSTMModel, TF_AVAILABLE
from src.ml.shared.models.model_config import LSTMConfig

logger = logging.getLogger(__name__)

AUC_THRESHOLD = 0.50

# Defaults MLS-LSTM (Quadir 2023 / KB-010)
DEFAULT_SEQUENCE_LENGTH = 30
DEFAULT_NUM_LAYERS = 2
DEFAULT_HIDDEN_UNITS = 64
DEFAULT_DROPOUT = 0.2
DEFAULT_HORIZON = 5


def add_target_up(
    df: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
    target_col: str = "target_up",
    use_cross_section: bool = True,
) -> pd.DataFrame:
    """
    Añade columna binaria target_up a partir de compute_target.

    Si hay columna ``ticker`` y use_cross_section=True:
        target_up = 1 si retorno 5d > mediana cross-seccional del universo.
    Si no:
        target_up = 1 si retorno 5d > 0.
    """
    out = df.copy()
    if "fwd_ret" not in out.columns:
        if "ticker" in out.columns:
            fwd_parts = []
            for _, grp in out.groupby("ticker", sort=False):
                raw = grp[["Open", "Close"]].copy()
                grp = grp.copy()
                grp["fwd_ret"] = compute_target(raw, horizon=horizon)
                fwd_parts.append(grp)
            out = pd.concat(fwd_parts).sort_index()
        else:
            raw = out[["Open", "Close"]].copy()
            out["fwd_ret"] = compute_target(raw, horizon=horizon)

    if use_cross_section and "ticker" in out.columns:
        g = out.groupby(out.index)
        out[target_col] = (g["fwd_ret"].rank(pct=True) > 0.5).astype(int)
    else:
        out[target_col] = (out["fwd_ret"] > 0).astype(int)

    return out


def build_sliding_sequences(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    sequence_length: int,
) -> tuple[np.ndarray, np.ndarray, pd.Index, np.ndarray | None]:
    """
    Construye secuencias (samples, seq_len, features) por ticker.

    Returns:
        X, y, index de la fila target, tickers por muestra (o None)
    """
    x_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    idx_parts: list[pd.Index] = []
    ticker_parts: list[str] = []
    track_tickers = "ticker" in df.columns

    groups = (
        df.groupby("ticker", sort=False)
        if track_tickers
        else [("_single", df)]
    )

    for ticker_name, grp in groups:
        grp = grp.sort_index()
        clean = grp.dropna(subset=feature_cols + [target_col])
        if len(clean) <= sequence_length:
            continue

        feats = clean[feature_cols].values.astype(np.float32)
        targets = clean[target_col].values.astype(np.float32)
        dates = clean.index
        label = ticker_name if track_tickers else "_single"

        for i in range(sequence_length, len(clean)):
            x_parts.append(feats[i - sequence_length : i])
            y_parts.append(targets[i])
            idx_parts.append(dates[i])
            ticker_parts.append(label)

    if not x_parts:
        empty_x = np.empty((0, sequence_length, len(feature_cols)), dtype=np.float32)
        return empty_x, np.empty((0,), dtype=np.float32), pd.Index([]), None

    tickers = np.array(ticker_parts) if track_tickers else None
    return (
        np.stack(x_parts),
        np.array(y_parts, dtype=np.float32),
        pd.Index(idx_parts),
        tickers,
    )


class LSTMSeqPredictor:
    """Predictor LSTM secuencial para P(up 5d) en producción."""

    def __init__(
        self,
        sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
        num_layers: int = DEFAULT_NUM_LAYERS,
        hidden_units: int = DEFAULT_HIDDEN_UNITS,
        dropout: float = DEFAULT_DROPOUT,
        epochs: int = 80,
        batch_size: int = 32,
        validation_split: float = 0.15,
        horizon: int = DEFAULT_HORIZON,
    ):
        self.sequence_length = sequence_length
        self.num_layers = num_layers
        self.hidden_units = hidden_units
        self.dropout = dropout
        self.epochs = epochs
        self.batch_size = batch_size
        self.validation_split = validation_split
        self.horizon = horizon

        self._model: Optional[LSTMModel] = None
        self._scaler = StandardScaler()
        self._feature_cols: list[str] = []
        self._target_col = "target_up"
        self._fitted = False
        self._last_metrics: dict = {}

        if not TF_AVAILABLE:
            logger.warning(
                "TensorFlow no instalado — LSTMSeqPredictor deshabilitado. "
                "Instalar con: pip install tensorflow"
            )

    @property
    def is_fitted(self) -> bool:
        return self._fitted and self._model is not None

    def _scale_frame(self, df: pd.DataFrame, feature_cols: list[str], fit: bool) -> pd.DataFrame:
        out = df.copy()
        values = out[feature_cols].values
        if fit:
            scaled = self._scaler.fit_transform(values)
        else:
            scaled = self._scaler.transform(values)
        out[feature_cols] = scaled
        return out

    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        target_col: str = "target_up",
        *,
        max_samples: int | None = None,
    ) -> dict:
        """
        Entrena MLS-LSTM sobre secuencias sliding-window.

        Args:
            max_samples: límite de secuencias (subsample aleatorio si excede).

        Returns:
            Dict con métricas de entrenamiento (train_auc, val_auc, n_samples, ...).
        """
        self._feature_cols = list(feature_cols)
        self._target_col = target_col
        self._fitted = False
        self._last_metrics = {"error": "tensorflow_not_available"}

        if not TF_AVAILABLE:
            return self._last_metrics

        work = df.copy()
        if target_col not in work.columns:
            work = add_target_up(work, horizon=self.horizon, target_col=target_col)

        work = self._scale_frame(work, feature_cols, fit=True)
        X, y, _, _ = build_sliding_sequences(
            work, feature_cols, target_col, self.sequence_length
        )

        if max_samples is not None and len(X) > max_samples:
            rng = np.random.default_rng(42)
            pick = np.sort(rng.choice(len(X), max_samples, replace=False))
            X, y = X[pick], y[pick]

        if len(X) < 50 or len(np.unique(y)) < 2:
            self._last_metrics = {
                "error": "insufficient_samples",
                "n_samples": int(len(X)),
            }
            return self._last_metrics

        split = int(len(X) * (1 - self.validation_split))
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        config = LSTMConfig(
            num_layers=self.num_layers,
            hidden_units=self.hidden_units,
            dropout_rate=self.dropout,
            sequence_length=self.sequence_length,
            prediction_horizon=self.horizon,
            learning_rate=0.001,
            batch_size=self.batch_size,
            epochs=self.epochs,
            optimizer="adam",
            task_type="classification",
            dense_activation="sigmoid",
            early_stopping_patience=5 if self.epochs <= 10 else 10,
            validation_split=self.validation_split,
        )

        self._model = LSTMModel(config)
        self._model.build(input_shape=(X.shape[1], X.shape[2]))
        self._model.fit(
            X_train,
            y_train,
            X_val if len(X_val) > 0 else None,
            y_val if len(y_val) > 0 else None,
            verbose=0,
        )
        self._fitted = True

        train_auc = 0.5
        val_auc = 0.5
        if len(np.unique(y_train)) > 1:
            p_tr = self._model.predict_proba(X_train)
            train_auc = float(roc_auc_score(y_train, p_tr))
        if len(X_val) > 0 and len(np.unique(y_val)) > 1:
            p_val = self._model.predict_proba(X_val)
            val_auc = float(roc_auc_score(y_val, p_val))

        self._last_metrics = {
            "n_samples": int(len(X)),
            "n_train": int(len(X_train)),
            "n_val": int(len(X_val)),
            "train_auc": round(train_auc, 4),
            "val_auc": round(val_auc, 4),
        }
        return self._last_metrics

    def predict_proba(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        *,
        align_panel: bool = True,
    ) -> np.ndarray:
        """
        Probabilidades P(up) en [0, 1].

        Si align_panel=True (default), devuelve array de len(df) con NaN donde
        no hay secuencia completa (para fusión en SuperModel).
        Si align_panel=False, devuelve solo filas secuenciales (legacy).
        """
        if align_panel:
            return self.predict_proba_panel(df, feature_cols)

        if not self.is_fitted:
            logger.warning("LSTMSeqPredictor no entrenado — devuelve 0.5")
            n = max(len(df) - self.sequence_length, 0)
            return np.full(max(n, 1), 0.5)

        work = self._scale_frame(df.copy(), feature_cols, fit=False)
        X, _, _, _ = build_sliding_sequences(
            work, feature_cols, self._target_col, self.sequence_length
        )
        if len(X) == 0:
            return np.array([0.5])
        return self._model.predict_proba(X)

    def predict_proba_panel(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
    ) -> np.ndarray:
        """Predicciones alineadas con len(df); NaN sin secuencia completa."""
        preds = np.full(len(df), np.nan)
        if not self.is_fitted:
            return preds

        work = df.copy()
        work["_pos"] = np.arange(len(df))
        work = self._scale_frame(work, feature_cols, fit=False)

        groups = (
            work.groupby("ticker", sort=False)
            if "ticker" in work.columns
            else [("_single", work)]
        )
        for _, grp in groups:
            grp = grp.sort_index()
            clean = grp.dropna(subset=feature_cols + [self._target_col])
            if len(clean) <= self.sequence_length:
                continue
            feats = clean[feature_cols].values.astype(np.float32)
            positions = clean["_pos"].values.astype(int)
            for i in range(self.sequence_length, len(clean)):
                window = feats[i - self.sequence_length : i]
                if np.any(np.isnan(window)):
                    continue
                X = window.reshape(1, self.sequence_length, len(feature_cols))
                preds[positions[i]] = float(self._model.predict_proba(X)[0])
        return preds

    def predict_proba_today(
        self,
        frames: dict[str, pd.DataFrame],
        feature_cols: list[str],
    ) -> dict[str, float]:
        """Última P(up) por ticker usando sequence_length filas finales."""
        if not self.is_fitted:
            return {}
        out: dict[str, float] = {}
        for name, raw_df in frames.items():
            clean = raw_df.dropna(subset=feature_cols)
            if len(clean) <= self.sequence_length:
                continue
            stub = clean.iloc[-self.sequence_length :].copy()
            stub[self._target_col] = 0
            stub["ticker"] = name
            p = self.predict_proba_panel(stub, feature_cols)
            last = p[~np.isnan(p)]
            if len(last):
                out[name] = float(last[-1])
        return out

    def evaluate_auc(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        target_col: str = "target_up",
        ticker_filter: str | None = None,
        eval_dates: pd.Index | None = None,
    ) -> float:
        """AUC ROC sobre secuencias (filtro opcional por ticker y/o fechas de eval)."""
        if not self.is_fitted:
            return 0.5

        work = df.copy()
        if target_col not in work.columns:
            work = add_target_up(work, horizon=self.horizon, target_col=target_col)

        work = self._scale_frame(work, feature_cols, fit=False)
        X, y, idx, tickers = build_sliding_sequences(
            work, feature_cols, target_col, self.sequence_length
        )
        if len(X) == 0:
            return 0.5

        mask = np.ones(len(y), dtype=bool)
        if ticker_filter and tickers is not None:
            mask &= tickers == ticker_filter
        if eval_dates is not None:
            mask &= np.isin(idx.values, eval_dates.values)

        X, y = X[mask], y[mask]
        if len(X) == 0 or len(np.unique(y)) < 2:
            return 0.5

        probs = self._model.predict_proba(X)
        return float(roc_auc_score(y, probs))
