"""
OHLCV Data Loader - Carga datos desde stage.precios_historicos
"""
import os
import sys
from pathlib import Path
from typing import Tuple, List, Optional
import pandas as pd
import pyodbc
from loguru import logger
from dotenv import load_dotenv

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.ml.shared.data_loaders.base_loader import BaseDataLoader


class OHLCVLoader(BaseDataLoader):
    """
    Carga datos OHLCV (Open, High, Low, Close, Volume) desde SQL Server
    Tabla: stage.precios_historicos
    """
    
    def __init__(
        self, 
        ticker_id: int, 
        ticker_symbol: str,
        server: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Args:
            ticker_id: ID del ticker en stage.cat_tickers
            ticker_symbol: Símbolo del ticker (ej: WALMEX*)
            server: SQL Server host (default: desde .env)
            database: Database name (default: desde .env)
            username: Username (default: desde .env)
            password: Password (default: desde .env)
        """
        super().__init__(ticker_id, ticker_symbol)
        
        # Cargar credenciales
        load_dotenv()
        self.server = server or os.getenv('SQL_SERVER')
        self.database = database or os.getenv('SQL_DATABASE')
        self.username = username or os.getenv('SQL_USER')
        self.password = password or os.getenv('SQL_PASSWORD')
        
        self._connection = None
    
    def connect(self):
        """Establecer conexión a SQL Server"""
        if self._connection is not None:
            return
        
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password}"
            )
            self._connection = pyodbc.connect(conn_str)
            logger.info(f"✅ Conectado a {self.server}/{self.database}")
        except Exception as e:
            logger.error(f"❌ Error conectando a SQL Server: {str(e)}")
            raise
    
    def disconnect(self):
        """Cerrar conexión"""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Conexión cerrada")
    
    def load_data(
        self, 
        start_date: str, 
        end_date: str,
        include_features: bool = False
    ) -> pd.DataFrame:
        """
        Cargar datos OHLCV desde stage.precios_historicos
        
        Args:
            start_date: Fecha inicio (YYYY-MM-DD)
            end_date: Fecha fin (YYYY-MM-DD)
            include_features: Si incluir indicadores técnicos (si existen)
            
        Returns:
            DataFrame con columnas: fecha, open, high, low, close, volume
        """
        self.connect()
        
        try:
            # Query base
            query = """
                SELECT 
                    fecha,
                    [open],
                    [high],
                    [low],
                    [close],
                    volume
                FROM stage.precios_historicos
                WHERE ticker_id = ?
                    AND fecha >= ?
                    AND fecha <= ?
                ORDER BY fecha ASC
            """
            
            logger.info(f"📊 Cargando datos de {self.ticker_symbol}: {start_date} a {end_date}")
            
            df = pd.read_sql_query(
                query, 
                self._connection, 
                params=(self.ticker_id, start_date, end_date)
            )
            
            if df.empty:
                logger.warning(f"⚠️  No se encontraron datos para ticker_id={self.ticker_id}")
                return df
            
            # Convertir fecha a datetime
            df['fecha'] = pd.to_datetime(df['fecha'])
            df.set_index('fecha', inplace=True)
            
            logger.success(f"✅ Cargados {len(df)} registros")
            logger.info(f"   Rango: {df.index[0]} a {df.index[-1]}")
            
            # Validar datos
            is_valid, errors = self.validate_data(df)
            if not is_valid:
                logger.warning(f"⚠️  Advertencias de validación:")
                for error in errors:
                    logger.warning(f"   - {error}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error cargando datos: {str(e)}")
            raise
        finally:
            self.disconnect()
    
    def validate_data(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validar integridad de datos OHLCV
        
        Validaciones:
        - Columnas requeridas presentes
        - No hay valores negativos en precios
        - High >= Low
        - High >= Open, Close
        - Low <= Open, Close
        - Volumen no negativo
        
        Args:
            df: DataFrame a validar
            
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Validar columnas requeridas
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            errors.append(f"Columnas faltantes: {missing_cols}")
            return False, errors
        
        # Validar valores negativos
        for col in ['open', 'high', 'low', 'close']:
            if (df[col] < 0).any():
                errors.append(f"Valores negativos en {col}")
        
        # Validar relaciones OHLC
        if (df['high'] < df['low']).any():
            count = (df['high'] < df['low']).sum()
            errors.append(f"High < Low en {count} registros")
        
        if (df['high'] < df['open']).any():
            count = (df['high'] < df['open']).sum()
            errors.append(f"High < Open en {count} registros")
        
        if (df['high'] < df['close']).any():
            count = (df['high'] < df['close']).sum()
            errors.append(f"High < Close en {count} registros")
        
        if (df['low'] > df['open']).any():
            count = (df['low'] > df['open']).sum()
            errors.append(f"Low > Open en {count} registros")
        
        if (df['low'] > df['close']).any():
            count = (df['low'] > df['close']).sum()
            errors.append(f"Low > Close en {count} registros")
        
        # Validar volumen
        if (df['volume'] < 0).any():
            errors.append("Volumen negativo encontrado")
        
        # Validar datos faltantes
        null_counts = df[required_cols].isnull().sum()
        if null_counts.any():
            for col, count in null_counts[null_counts > 0].items():
                errors.append(f"{count} valores nulos en {col}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def get_latest_date(self) -> Optional[str]:
        """
        Obtener la fecha más reciente con datos disponibles
        
        Returns:
            Fecha en formato YYYY-MM-DD o None si no hay datos
        """
        self.connect()
        
        try:
            query = """
                SELECT MAX(fecha) as max_fecha
                FROM stage.precios_historicos
                WHERE ticker_id = ?
            """
            
            cursor = self._connection.cursor()
            cursor.execute(query, (self.ticker_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                return result[0].strftime('%Y-%m-%d')
            return None
            
        finally:
            self.disconnect()
    
    def get_data_summary(self) -> dict:
        """
        Obtener resumen estadístico de los datos disponibles
        
        Returns:
            Dict con estadísticas básicas
        """
        self.connect()
        
        try:
            query = """
                SELECT 
                    COUNT(*) as total_registros,
                    MIN(fecha) as fecha_inicio,
                    MAX(fecha) as fecha_fin,
                    MIN([close]) as precio_min,
                    MAX([close]) as precio_max,
                    AVG([close]) as precio_promedio,
                    SUM(volume) as volumen_total
                FROM stage.precios_historicos
                WHERE ticker_id = ?
            """
            
            cursor = self._connection.cursor()
            cursor.execute(query, (self.ticker_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'total_registros': result[0],
                    'fecha_inicio': result[1].strftime('%Y-%m-%d') if result[1] else None,
                    'fecha_fin': result[2].strftime('%Y-%m-%d') if result[2] else None,
                    'precio_min': float(result[3]) if result[3] else None,
                    'precio_max': float(result[4]) if result[4] else None,
                    'precio_promedio': float(result[5]) if result[5] else None,
                    'volumen_total': int(result[6]) if result[6] else None
                }
            return {}
            
        finally:
            self.disconnect()
