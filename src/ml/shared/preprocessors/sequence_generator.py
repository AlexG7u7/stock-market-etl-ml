"""
Sequence generator for LSTM models
"""
import numpy as np
from typing import Tuple
from loguru import logger


class SequenceGenerator:
    """
    Genera secuencias de datos para modelos LSTM
    
    Convierte series temporales en formato:
    X: (samples, sequence_length, features)
    y: (samples, prediction_horizon)
    
    Ejemplo:
        sequence_length = 60 (últimos 60 días)
        prediction_horizon = 5 (predecir 5 días adelante)
        
        X[0] = [día_0:día_59]  → y[0] = día_64 (día 59 + 5)
        X[1] = [día_1:día_60]  → y[1] = día_65
        ...
    """
    
    def __init__(
        self, 
        sequence_length: int = 60,
        prediction_horizon: int = 5,
        stride: int = 1
    ):
        """
        Args:
            sequence_length: Número de pasos temporales de entrada (lookback)
            prediction_horizon: Días adelante a predecir (default: 5)
            stride: Paso entre secuencias (default: 1 = todas las ventanas posibles)
        """
        self.sequence_length = sequence_length
        self.prediction_horizon = prediction_horizon
        self.stride = stride
    
    def create_sequences(
        self, 
        data: np.ndarray,
        target_column_idx: int = 0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Crear secuencias para LSTM
        
        Args:
            data: Array 2D (timesteps, features) - Ya debe estar escalado
            target_column_idx: Índice de la columna a predecir (default: 0 = close)
            
        Returns:
            (X, y) donde:
                X shape: (samples, sequence_length, features)
                y shape: (samples,) - precio a predecir
        """
        X, y = [], []
        
        # Calcular cuántas secuencias podemos crear
        max_idx = len(data) - self.sequence_length - self.prediction_horizon + 1
        
        for i in range(0, max_idx, self.stride):
            # Secuencia de entrada (lookback window)
            X_seq = data[i : i + self.sequence_length]
            
            # Target: precio en t + prediction_horizon
            y_val = data[i + self.sequence_length + self.prediction_horizon - 1, target_column_idx]
            
            X.append(X_seq)
            y.append(y_val)
        
        X = np.array(X)
        y = np.array(y)
        
        logger.info(f"✅ Secuencias creadas:")
        logger.info(f"   X shape: {X.shape} (samples, sequence_length, features)")
        logger.info(f"   y shape: {y.shape}")
        logger.info(f"   Total samples: {len(X)}")
        
        return X, y
    
    def create_multi_horizon_sequences(
        self,
        data: np.ndarray,
        horizons: list = [5, 10, 15],
        target_column_idx: int = 0
    ) -> dict:
        """
        Crear secuencias para múltiples horizontes de predicción
        
        Args:
            data: Array 2D (timesteps, features)
            horizons: Lista de horizontes (ej: [5, 10, 15] días)
            target_column_idx: Índice de columna target
            
        Returns:
            Dict con keys: 'X', 'y_5d', 'y_10d', 'y_15d'
        """
        X, y_dict = [], {f'y_{h}d': [] for h in horizons}
        
        # Usar el horizonte máximo para calcular límite
        max_horizon = max(horizons)
        max_idx = len(data) - self.sequence_length - max_horizon + 1
        
        for i in range(0, max_idx, self.stride):
            # Secuencia de entrada (común para todos los horizontes)
            X_seq = data[i : i + self.sequence_length]
            X.append(X_seq)
            
            # Targets para cada horizonte
            for horizon in horizons:
                y_val = data[i + self.sequence_length + horizon - 1, target_column_idx]
                y_dict[f'y_{horizon}d'].append(y_val)
        
        result = {'X': np.array(X)}
        for key in y_dict:
            result[key] = np.array(y_dict[key])
        
        logger.info(f"✅ Secuencias multi-horizonte creadas:")
        logger.info(f"   X shape: {result['X'].shape}")
        for horizon in horizons:
            logger.info(f"   y_{horizon}d shape: {result[f'y_{horizon}d'].shape}")
        
        return result
    
    def get_last_sequence(
        self, 
        data: np.ndarray
    ) -> np.ndarray:
        """
        Obtener la última secuencia disponible (para predicción en producción)
        
        Args:
            data: Array 2D (timesteps, features)
            
        Returns:
            Array 3D (1, sequence_length, features) - listo para predicción
        """
        if len(data) < self.sequence_length:
            raise ValueError(
                f"Datos insuficientes: {len(data)} < {self.sequence_length}"
            )
        
        last_sequence = data[-self.sequence_length:]
        
        # Reshape para batch dimension
        return last_sequence.reshape(1, self.sequence_length, -1)
    
    def validate_shapes(self, X: np.ndarray, y: np.ndarray):
        """
        Validar que las formas de X e y sean correctas
        
        Args:
            X: Array de secuencias
            y: Array de targets
            
        Raises:
            ValueError si las formas no son correctas
        """
        if len(X.shape) != 3:
            raise ValueError(f"X debe ser 3D, got shape {X.shape}")
        
        if X.shape[1] != self.sequence_length:
            raise ValueError(
                f"X sequence_length debe ser {self.sequence_length}, got {X.shape[1]}"
            )
        
        if len(X) != len(y):
            raise ValueError(
                f"X y y deben tener mismo número de samples: {len(X)} != {len(y)}"
            )
        
        logger.success("✅ Shapes validadas correctamente")
