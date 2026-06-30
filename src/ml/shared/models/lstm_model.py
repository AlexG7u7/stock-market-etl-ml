"""
LSTM Model Architecture
"""
import numpy as np
from typing import Tuple, Optional
from pathlib import Path

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, regularizers, callbacks
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️  TensorFlow no instalado. Instalar con: pip install tensorflow")

from loguru import logger
from .model_config import LSTMConfig


class LSTMModel:
    """
    Modelo LSTM parametrizable para predicción de series temporales
    
    Arquitectura:
        Input → LSTM Layers → Dropout → Dense → Output
    """
    
    def __init__(self, config: LSTMConfig):
        """
        Args:
            config: Configuración del modelo (LSTMConfig)
        """
        if not TF_AVAILABLE:
            raise ImportError("TensorFlow es requerido para LSTMModel")
        
        self.config = config
        self.config.validate()
        
        self.model = None
        self.history = None
        self._is_trained = False
    
    def build(self, input_shape: Tuple[int, int]):
        """
        Construir arquitectura del modelo
        
        Args:
            input_shape: (sequence_length, num_features)
        """
        logger.info("🏗️  Construyendo modelo LSTM...")
        logger.info(f"   Input shape: {input_shape}")
        logger.info(f"   Num layers: {self.config.num_layers}")
        logger.info(f"   Hidden units: {self.config.hidden_units}")
        logger.info(f"   Dropout: {self.config.dropout_rate}")
        
        model = keras.Sequential(name='LSTM_Predictor')
        
        # Input layer
        model.add(layers.Input(shape=input_shape))
        
        # LSTM Layers
        for i in range(self.config.num_layers):
            # Determinar si retornar secuencias (todas las capas excepto la última)
            return_sequences = (i < self.config.num_layers - 1)
            
            model.add(layers.LSTM(
                units=self.config.hidden_units,
                return_sequences=return_sequences,
                recurrent_dropout=self.config.recurrent_dropout,
                kernel_regularizer=regularizers.l1_l2(
                    l1=self.config.l1_reg,
                    l2=self.config.l2_reg
                ),
                name=f'lstm_{i+1}'
            ))
            
            # Dropout después de cada LSTM
            if self.config.dropout_rate > 0:
                model.add(layers.Dropout(
                    self.config.dropout_rate,
                    name=f'dropout_{i+1}'
                ))
        
        # Dense output layer
        is_classification = self._is_classification()
        output_activation = 'sigmoid' if is_classification else self.config.dense_activation
        model.add(layers.Dense(
            units=1,
            activation=output_activation,
            name='output'
        ))
        
        # Compilar modelo
        optimizer = self._get_optimizer()
        if is_classification:
            model.compile(
                optimizer=optimizer,
                loss='binary_crossentropy',
                metrics=[keras.metrics.AUC(name='auc')],
            )
        else:
            model.compile(
                optimizer=optimizer,
                loss='mse',
                metrics=['mae', 'mape'],
            )
        
        self.model = model
        
        logger.success(f"✅ Modelo construido: {model.count_params():,} parámetros")
        
        return self
    
    def _is_classification(self) -> bool:
        """True si el modelo predice P(up) binaria."""
        return (
            self.config.task_type == 'classification'
            or self.config.dense_activation == 'sigmoid'
        )

    def _get_optimizer(self):
        """Obtener optimizador configurado"""
        if self.config.optimizer == 'adam':
            return keras.optimizers.Adam(learning_rate=self.config.learning_rate)
        elif self.config.optimizer == 'rmsprop':
            return keras.optimizers.RMSprop(learning_rate=self.config.learning_rate)
        elif self.config.optimizer == 'sgd':
            return keras.optimizers.SGD(learning_rate=self.config.learning_rate)
        else:
            raise ValueError(f"Optimizador desconocido: {self.config.optimizer}")
    
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        verbose: int = 1
    ):
        """
        Entrenar el modelo
        
        Args:
            X_train: Array (samples, sequence_length, features)
            y_train: Array (samples,)
            X_val: Validation data (opcional)
            y_val: Validation targets (opcional)
            verbose: Verbosity level (0=silent, 1=progress, 2=one line/epoch)
        """
        if self.model is None:
            raise ValueError("Modelo no construido. Llamar .build() primero")
        
        logger.info("🎓 Entrenando modelo...")
        logger.info(f"   Train samples: {len(X_train)}")
        if X_val is not None:
            logger.info(f"   Val samples: {len(X_val)}")
        logger.info(f"   Batch size: {self.config.batch_size}")
        logger.info(f"   Epochs: {self.config.epochs}")
        
        # Callbacks
        callback_list = self._get_callbacks()
        
        # Validation data
        validation_data = None
        if X_val is not None and y_val is not None:
            validation_data = (X_val, y_val)
        
        # Train
        self.history = self.model.fit(
            X_train,
            y_train,
            batch_size=self.config.batch_size,
            epochs=self.config.epochs,
            validation_data=validation_data,
            callbacks=callback_list,
            verbose=verbose
        )
        
        self._is_trained = True
        
        logger.success("✅ Entrenamiento completado")
        
        # Log final metrics
        final_metrics: dict[str, float] = {'train_loss': self.history.history['loss'][-1]}
        if self._is_classification():
            if 'auc' in self.history.history:
                final_metrics['train_auc'] = self.history.history['auc'][-1]
        else:
            final_metrics['train_mae'] = self.history.history['mae'][-1]

        if validation_data:
            final_metrics['val_loss'] = self.history.history['val_loss'][-1]
            if self._is_classification() and 'val_auc' in self.history.history:
                final_metrics['val_auc'] = self.history.history['val_auc'][-1]
            elif not self._is_classification():
                final_metrics['val_mae'] = self.history.history['val_mae'][-1]

        logger.info("📊 Métricas finales:")
        for metric, value in final_metrics.items():
            logger.info(f"   {metric}: {value:.4f}")
        
        return self.history

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        verbose: int = 1,
    ):
        """Alias de train() para API sklearn-like."""
        return self.train(X_train, y_train, X_val, y_val, verbose=verbose)
    
    def _get_callbacks(self) -> list:
        """Crear callbacks para entrenamiento"""
        callback_list = []
        
        # Early Stopping
        if self.config.early_stopping_patience > 0:
            early_stop = callbacks.EarlyStopping(
                monitor='val_loss',
                patience=self.config.early_stopping_patience,
                min_delta=self.config.early_stopping_min_delta,
                restore_best_weights=self.config.restore_best_weights,
                verbose=0,
            )
            callback_list.append(early_stop)
        
        # ReduceLROnPlateau
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=10,
            min_lr=1e-7,
            verbose=0,
        )
        callback_list.append(reduce_lr)
        
        return callback_list
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Hacer predicciones
        
        Args:
            X: Array (samples, sequence_length, features)
            
        Returns:
            Array de predicciones (samples,)
        """
        if not self._is_trained:
            logger.warning("⚠️  Modelo no entrenado aún")
        
        predictions = self.model.predict(X, verbose=0)
        return predictions.flatten()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Probabilidades P(up) en [0, 1] para clasificación binaria.

        Returns:
            Array 1D de probabilidades (samples,)
        """
        if not self._is_classification():
            logger.warning("predict_proba() en modelo de regresión — devuelve predict() sin calibrar")
        return self.predict(X)
    
    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> dict:
        """
        Evaluar modelo en test set
        
        Args:
            X_test: Test sequences
            y_test: Test targets
            
        Returns:
            Dict con métricas
        """
        logger.info("📊 Evaluando modelo en test set...")

        test_metrics = self.model.evaluate(X_test, y_test, verbose=0)
        y_pred = self.predict(X_test)

        if self._is_classification():
            from sklearn.metrics import roc_auc_score, log_loss

            auc = roc_auc_score(y_test, y_pred) if len(np.unique(y_test)) > 1 else 0.5
            metrics = {
                'loss': test_metrics[0],
                'auc': auc,
                'log_loss': log_loss(y_test, np.clip(y_pred, 1e-7, 1 - 1e-7)),
            }
        else:
            from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100
            metrics = {
                'loss': test_metrics[0],
                'rmse': rmse,
                'mae': mae,
                'mape': mape,
                'r2': r2,
            }

        logger.info("   Métricas de test:")
        for metric, value in metrics.items():
            logger.info(f"      {metric}: {value:.4f}")

        return metrics
    
    def save(self, filepath: str):
        """
        Guardar modelo a disco
        
        Args:
            filepath: Ruta donde guardar (.keras o .h5)
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        self.model.save(filepath)
        
        logger.info(f"💾 Modelo guardado en {filepath}")
    
    @classmethod
    def load(cls, filepath: str, config: LSTMConfig) -> 'LSTMModel':
        """
        Cargar modelo desde disco
        
        Args:
            filepath: Ruta del modelo guardado
            config: Configuración del modelo
            
        Returns:
            Instancia de LSTMModel
        """
        instance = cls(config)
        instance.model = keras.models.load_model(filepath)
        instance._is_trained = True
        
        logger.info(f"📂 Modelo cargado desde {filepath}")
        
        return instance
    
    def summary(self):
        """Mostrar resumen del modelo"""
        if self.model is None:
            logger.warning("⚠️  Modelo no construido")
            return
        
        self.model.summary()
    
    def get_config_dict(self) -> dict:
        """Obtener configuración como diccionario"""
        return self.config.to_dict()
