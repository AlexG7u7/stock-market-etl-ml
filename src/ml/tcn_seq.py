"""
TCN-LSTM secuencial — alternativa a LSTMSeqPredictor (Dudukcu 2023 / KB-070).

Misma interfaz que lstm_seq para walk-forward y SuperModel.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.ml.lstm_seq import (
    DEFAULT_HORIZON,
    add_target_up,
    build_sliding_sequences,
)
from src.ml.shared.models.tcn_model import TCNConfig, TCNModel, TF_AVAILABLE

logger = logging.getLogger(__name__)

AUC_THRESHOLD = 0.50
DEFAULT_SEQUENCE_LENGTH = 30


class TCNSeqPredictor:
    """Predictor TCN-LSTM para P(up 5d)."""

    def __init__(
        self,
        sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
        filters: int = 64,
        num_tcn_blocks: int = 3,
        lstm_units: int = 64,
        dropout: float = 0.2,
        epochs: int = 80,
        batch_size: int = 32,
        validation_split: float = 0.15,
        horizon: int = DEFAULT_HORIZON,
    ):
        self.sequence_length = sequence_length
        self.filters = filters
        self.num_tcn_blocks = num_tcn_blocks
        self.lstm_units = lstm_units
        self.dropout = dropout
        self.epochs = epochs
        self.batch_size = batch_size
        self.validation_split = validation_split
        self.horizon = horizon

        self._model: Optional[TCNModel] = None
        self._scaler = StandardScaler()
        self._feature_cols: list[str] = []
        self._target_col = "target_up"
        self._fitted = False
        self._last_metrics: dict = {}

        if not TF_AVAILABLE:
            logger.warning("TensorFlow no instalado — TCNSeqPredictor deshabilitado")

    @property
    def is_fitted(self) -> bool:
        return self._fitted and self._model is not None

    def _scale_frame(self, df: pd.DataFrame, feature_cols: list[str], fit: bool) -> pd.DataFrame:
        out = df.copy()
        values = out[feature_cols].values
        out[feature_cols] = self._scaler.fit_transform(values) if fit else self._scaler.transform(values)
        return out

    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        target_col: str = "target_up",
        *,
        max_samples: int | None = None,
    ) -> dict:
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
        X, y, _, _ = build_sliding_sequences(work, feature_cols, target_col, self.sequence_length)

        if max_samples is not None and len(X) > max_samples:
            rng = np.random.default_rng(42)
            pick = np.sort(rng.choice(len(X), max_samples, replace=False))
            X, y = X[pick], y[pick]

        if len(X) < 50 or len(np.unique(y)) < 2:
            self._last_metrics = {"error": "insufficient_samples", "n_samples": int(len(X))}
            return self._last_metrics

        split = int(len(X) * (1 - self.validation_split))
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        config = TCNConfig(
            filters=self.filters,
            num_tcn_blocks=self.num_tcn_blocks,
            lstm_units=self.lstm_units,
            dropout_rate=self.dropout,
            batch_size=self.batch_size,
            epochs=self.epochs,
            early_stopping_patience=5 if self.epochs <= 10 else 10,
        )
        self._model = TCNModel(config)
        self._model.build(input_shape=(X.shape[1], X.shape[2]))
        self._model.fit(
            X_train, y_train,
            X_val if len(X_val) > 0 else None,
            y_val if len(y_val) > 0 else None,
            verbose=0,
        )
        self._fitted = True

        train_auc = val_auc = 0.5
        if len(np.unique(y_train)) > 1:
            train_auc = float(roc_auc_score(y_train, self._model.predict_proba(X_train)))
        if len(X_val) > 0 and len(np.unique(y_val)) > 1:
            val_auc = float(roc_auc_score(y_val, self._model.predict_proba(X_val)))

        self._last_metrics = {
            "n_samples": int(len(X)),
            "train_auc": round(train_auc, 4),
            "val_auc": round(val_auc, 4),
        }
        return self._last_metrics

    def predict_proba_panel(self, df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
        preds = np.full(len(df), np.nan)
        if not self.is_fitted:
            return preds

        work = df.copy()
        work["_pos"] = np.arange(len(df))
        work = self._scale_frame(work, feature_cols, fit=False)
        groups = work.groupby("ticker", sort=False) if "ticker" in work.columns else [("_single", work)]

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

    def evaluate_auc(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        target_col: str = "target_up",
        ticker_filter: str | None = None,
        eval_dates: pd.Index | None = None,
    ) -> float:
        if not self.is_fitted:
            return 0.5

        work = df.copy()
        if target_col not in work.columns:
            work = add_target_up(work, horizon=self.horizon, target_col=target_col)
        work = self._scale_frame(work, feature_cols, fit=False)
        X, y, idx, tickers = build_sliding_sequences(
            work, feature_cols, target_col, self.sequence_length,
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
        return float(roc_auc_score(y, self._model.predict_proba(X)))
