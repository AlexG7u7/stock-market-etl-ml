"""
Scalers for data normalization
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
import pickle
from pathlib import Path
from loguru import logger


class DataScaler:
    """
    Wrapper para scalers de sklearn con capacidad de guardar/cargar
    
    Soporta:
    - MinMaxScaler: Escala a rango [0, 1] o custom
    - StandardScaler: Z-score normalization (mean=0, std=1)
    - RobustScaler: Usa mediana y IQR (robusto a outliers)
    """
    
    def __init__(self, scaler_type: str = 'minmax', feature_range: Tuple[int, int] = (0, 1)):
        """
        Args:
            scaler_type: 'minmax', 'standard', 'robust'
            feature_range: Rango para MinMaxScaler (default: [0, 1])
        """
        self.scaler_type = scaler_type
        self.feature_range = feature_range
        self.scaler = None
        self.feature_names = None
        
        self._initialize_scaler()
    
    def _initialize_scaler(self):
        """Inicializar el scaler según tipo"""
        if self.scaler_type == 'minmax':
            self.scaler = MinMaxScaler(feature_range=self.feature_range)
        elif self.scaler_type == 'standard':
            self.scaler = StandardScaler()
        elif self.scaler_type == 'robust':
            self.scaler = RobustScaler()
        else:
            raise ValueError(f"Scaler type desconocido: {self.scaler_type}")
    
    def fit(self, data: pd.DataFrame) -> 'DataScaler':
        """
        Ajustar scaler a los datos de entrenamiento
        
        Args:
            data: DataFrame con features a escalar
            
        Returns:
            Self para method chaining
        """
        self.feature_names = list(data.columns)
        self.scaler.fit(data)
        
        logger.info(f"✅ Scaler '{self.scaler_type}' ajustado a {len(self.feature_names)} features")
        
        return self
    
    def transform(self, data: pd.DataFrame) -> np.ndarray:
        """
        Transformar datos usando scaler ya ajustado
        
        Args:
            data: DataFrame a transformar
            
        Returns:
            Array numpy escalado
        """
        if self.scaler is None:
            raise ValueError("Scaler no ha sido ajustado. Llamar .fit() primero")
        
        # Verificar que las columnas coincidan
        if list(data.columns) != self.feature_names:
            logger.warning("⚠️  Columnas no coinciden. Reordenando...")
            data = data[self.feature_names]
        
        return self.scaler.transform(data)
    
    def fit_transform(self, data: pd.DataFrame) -> np.ndarray:
        """
        Ajustar y transformar en un solo paso
        
        Args:
            data: DataFrame a escalar
            
        Returns:
            Array numpy escalado
        """
        self.fit(data)
        return self.transform(data)
    
    def inverse_transform(self, data: np.ndarray) -> np.ndarray:
        """
        Revertir escalado (volver a escala original)
        
        Args:
            data: Array escalado
            
        Returns:
            Array en escala original
        """
        if self.scaler is None:
            raise ValueError("Scaler no ha sido ajustado")
        
        return self.scaler.inverse_transform(data)
    
    def save(self, filepath: str):
        """
        Guardar scaler a disco
        
        Args:
            filepath: Ruta donde guardar el scaler (.pkl)
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump({
                'scaler': self.scaler,
                'scaler_type': self.scaler_type,
                'feature_range': self.feature_range,
                'feature_names': self.feature_names
            }, f)
        
        logger.info(f"💾 Scaler guardado en {filepath}")
    
    @classmethod
    def load(cls, filepath: str) -> 'DataScaler':
        """
        Cargar scaler desde disco
        
        Args:
            filepath: Ruta del scaler guardado
            
        Returns:
            Instancia de DataScaler
        """
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        
        instance = cls(
            scaler_type=data['scaler_type'],
            feature_range=data['feature_range']
        )
        instance.scaler = data['scaler']
        instance.feature_names = data['feature_names']
        
        logger.info(f"📂 Scaler cargado desde {filepath}")
        
        return instance
    
    def get_params(self) -> dict:
        """
        Obtener parámetros del scaler (útil para logging)
        
        Returns:
            Dict con parámetros
        """
        params = {
            'scaler_type': self.scaler_type,
            'num_features': len(self.feature_names) if self.feature_names else 0
        }
        
        if self.scaler_type == 'minmax':
            params['feature_range'] = self.feature_range
            if hasattr(self.scaler, 'data_min_'):
                params['data_min'] = self.scaler.data_min_.tolist()
                params['data_max'] = self.scaler.data_max_.tolist()
        
        elif self.scaler_type == 'standard':
            if hasattr(self.scaler, 'mean_'):
                params['mean'] = self.scaler.mean_.tolist()
                params['std'] = self.scaler.scale_.tolist()
        
        return params


def create_scaler(config: dict) -> DataScaler:
    """
    Factory function para crear scaler desde configuración
    
    Args:
        config: Dict con configuración (de YAML)
        
    Returns:
        Instancia de DataScaler
    """
    scaler_type = config.get('scaler_type', 'minmax')
    feature_range = tuple(config.get('feature_range', [0, 1]))
    
    return DataScaler(scaler_type=scaler_type, feature_range=feature_range)
