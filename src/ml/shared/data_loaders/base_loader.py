"""
Base abstract class for data loaders
"""
from abc import ABC, abstractmethod
from typing import Tuple, List, Optional
import pandas as pd


class BaseDataLoader(ABC):
    """
    Clase base abstracta para todos los data loaders
    
    Responsabilidades:
    - Conectar a fuente de datos (SQL Server, archivos, API, etc.)
    - Cargar datos históricos de precios
    - Validar integridad de datos
    - Manejar datos faltantes
    """
    
    def __init__(self, ticker_id: int, ticker_symbol: str):
        """
        Args:
            ticker_id: ID del ticker en la base de datos
            ticker_symbol: Símbolo del ticker (ej: WALMEX*, ALSEA*)
        """
        self.ticker_id = ticker_id
        self.ticker_symbol = ticker_symbol
    
    @abstractmethod
    def load_data(
        self, 
        start_date: str, 
        end_date: str,
        include_features: bool = False
    ) -> pd.DataFrame:
        """
        Cargar datos históricos en un rango de fechas
        
        Args:
            start_date: Fecha inicio (YYYY-MM-DD)
            end_date: Fecha fin (YYYY-MM-DD)
            include_features: Si incluir features técnicos pre-calculados
            
        Returns:
            DataFrame con columnas: fecha, open, high, low, close, volume, ...
        """
        pass
    
    @abstractmethod
    def validate_data(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validar integridad de datos
        
        Args:
            df: DataFrame a validar
            
        Returns:
            (is_valid, list_of_errors)
        """
        pass
    
    def handle_missing_data(
        self, 
        df: pd.DataFrame, 
        method: str = 'ffill'
    ) -> pd.DataFrame:
        """
        Manejar datos faltantes
        
        Args:
            df: DataFrame con posibles valores faltantes
            method: 'ffill', 'bfill', 'interpolate', 'drop'
            
        Returns:
            DataFrame sin valores faltantes
        """
        if method == 'ffill':
            return df.fillna(method='ffill')
        elif method == 'bfill':
            return df.fillna(method='bfill')
        elif method == 'interpolate':
            return df.interpolate(method='linear')
        elif method == 'drop':
            return df.dropna()
        else:
            raise ValueError(f"Método desconocido: {method}")
    
    def get_feature_columns(self) -> List[str]:
        """
        Retorna lista de columnas de features disponibles
        
        Returns:
            Lista de nombres de columnas
        """
        return [
            'open', 'high', 'low', 'close', 'volume',
            # Features técnicos (si están disponibles)
            'rsi_14', 'macd', 'macd_signal', 
            'bb_upper', 'bb_middle', 'bb_lower',
            'sma_20', 'sma_50', 'ema_12', 'ema_26',
            'returns_1d', 'returns_5d', 'volatility_21d'
        ]
