"""
TCN-LSTM hybrid — Dudukcu et al. 2023 (KB-070).

TCN (convoluciones causales dilatadas) → LSTM → P(up).
Misma API que LSTMModel para drop-in en walk-forward CV.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, callbacks, regularizers
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

from loguru import logger


@dataclass
class TCNConfig:
    filters: int = 64
    kernel_size: int = 3
    num_tcn_blocks: int = 3
    dilation_base: int = 2
    lstm_units: int = 64
    dropout_rate: float = 0.2
    l2_reg: float = 0.01
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 80
    optimizer: str = "adam"
    early_stopping_patience: int = 10
    early_stopping_min_delta: float = 0.0001
    restore_best_weights: bool = True
    task_type: str = "classification"


class TCNModel:
    """TCN → LSTM classifier for sequential financial features."""

    def __init__(self, config: TCNConfig):
        if not TF_AVAILABLE:
            raise ImportError("TensorFlow es requerido para TCNModel")
        self.config = config
        self.model: keras.Model | None = None
        self.history = None
        self._is_trained = False

    def build(self, input_shape: tuple[int, int]) -> TCNModel:
        cfg = self.config
        inp = keras.Input(shape=input_shape, name="seq_input")
        x = inp

        for i in range(cfg.num_tcn_blocks):
            dilation = cfg.dilation_base ** i
            y = layers.Conv1D(
                cfg.filters,
                cfg.kernel_size,
                padding="causal",
                dilation_rate=dilation,
                kernel_regularizer=regularizers.l2(cfg.l2_reg),
                name=f"tcn_conv_{i+1}",
            )(x)
            y = layers.BatchNormalization(name=f"tcn_bn_{i+1}")(y)
            y = layers.Activation("relu", name=f"tcn_relu_{i+1}")(y)
            y = layers.Dropout(cfg.dropout_rate, name=f"tcn_drop_{i+1}")(y)
            x = y

        x = layers.LSTM(
            cfg.lstm_units,
            kernel_regularizer=regularizers.l2(cfg.l2_reg),
            name="tcn_lstm",
        )(x)
        x = layers.Dropout(cfg.dropout_rate, name="tcn_lstm_drop")(x)
        out_act = "sigmoid" if cfg.task_type == "classification" else "linear"
        out = layers.Dense(1, activation=out_act, name="output")(x)

        model = keras.Model(inp, out, name="TCN_LSTM_Predictor")
        opt = keras.optimizers.Adam(learning_rate=cfg.learning_rate)
        if cfg.task_type == "classification":
            model.compile(
                optimizer=opt,
                loss="binary_crossentropy",
                metrics=[keras.metrics.AUC(name="auc")],
            )
        else:
            model.compile(optimizer=opt, loss="mse", metrics=["mae"])

        self.model = model
        logger.info(f"TCN-LSTM built: {model.count_params():,} params")
        return self

    def _callback_list(self) -> list:
        cbs: list = []
        if self.config.early_stopping_patience > 0:
            cbs.append(
                callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=self.config.early_stopping_patience,
                    min_delta=self.config.early_stopping_min_delta,
                    restore_best_weights=self.config.restore_best_weights,
                    verbose=0,
                )
            )
        cbs.append(
            callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=8, min_lr=1e-7, verbose=0,
            )
        )
        return cbs

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        verbose: int = 0,
    ):
        if self.model is None:
            raise ValueError("Modelo no construido — llamar build() primero")
        val = (X_val, y_val) if X_val is not None and y_val is not None else None
        self.history = self.model.fit(
            X_train,
            y_train,
            validation_data=val,
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            callbacks=self._callback_list(),
            verbose=verbose,
        )
        self._is_trained = True
        return self.history

    def fit(self, X_train, y_train, X_val=None, y_val=None, verbose=0):
        return self.train(X_train, y_train, X_val, y_val, verbose)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._is_trained or self.model is None:
            raise ValueError("Modelo no entrenado")
        raw = self.model.predict(X, verbose=0).flatten()
        return np.clip(raw.astype(np.float64), 0.0, 1.0)
