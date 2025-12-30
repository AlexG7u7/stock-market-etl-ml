"""
Prediction Pipeline - Pipeline para generar predicciones en producción
"""
import yaml
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import pyodbc

from ..shared.data_loaders.ohlcv_loader import OHLCVLoader
from ..shared.data_loaders.feature_engineering import FeatureEngineer
from ..shared.preprocessors.scaler import DataScaler
from ..shared.preprocessors.sequence_generator import SequenceGenerator
from ..shared.persistence.model_registry import ModelRegistry


class PredictionPipeline:
    """
    Pipeline para generar predicciones con modelo en producción:
    1. Cargar modelo de producción
    2. Obtener últimos datos
    3. Feature engineering
    4. Preprocesar
    5. Predecir próximos N días
    6. Guardar predicciones en ml.predictions
    """
    
    def __init__(self, config_path: str = "src/ml/config/training_config.yml"):
        """
        Args:
            config_path: Path al archivo de configuración
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        self.model_registry = None
        self.data_loader = None
        self.feature_engineer = None
        self.scaler = None
        self.sequence_generator = None
    
    def _load_config(self) -> Dict:
        """Cargar configuración desde YAML"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def run(
        self,
        ticker: str,
        horizon_days: int = 5,
        model_id: Optional[int] = None
    ) -> Dict:
        """
        Generar predicciones para próximos N días
        
        Args:
            ticker: Símbolo del ticker
            horizon_days: Días a predecir
            model_id: ID del modelo a usar (si None, usa modelo en producción)
            
        Returns:
            Dict con predicciones
        """
        logger.info("=" * 80)
        logger.info("🔮 PREDICTION PIPELINE - INICIO")
        logger.info("=" * 80)
        logger.info(f"Ticker: {ticker}")
        logger.info(f"Horizon: {horizon_days} días")
        logger.info("")
        
        # 1. Cargar modelo
        logger.info("📦 PASO 1: Cargar modelo...")
        model, config, model_id = self._load_model(ticker, horizon_days, model_id)
        logger.success(f"✅ Modelo {model_id} cargado")
        
        # 2. Obtener datos más recientes
        logger.info("\n📊 PASO 2: Obtener datos recientes...")
        ticker_id = self._get_ticker_id(ticker)
        data = self._load_recent_data(ticker)
        logger.success(f"✅ {len(data)} registros cargados")
        
        # 3. Feature engineering
        logger.info("\n🔧 PASO 3: Feature engineering...")
        data_with_features = self._add_features(data)
        
        # 4. Preprocesar
        logger.info("\n⚙️  PASO 4: Preprocesamiento...")
        last_sequence = self._create_last_sequence(data_with_features, config)
        
        # 5. Predecir
        logger.info("\n🔮 PASO 5: Generar predicciones...")
        predictions = self._predict(model, last_sequence, horizon_days)
        
        # 6. Guardar predicciones
        logger.info("\n💾 PASO 6: Guardar predicciones...")
        self._save_predictions(
            model_id=model_id,
            ticker_id=ticker_id,
            predictions=predictions,
            horizon_days=horizon_days
        )
        
        logger.info("\n" + "=" * 80)
        logger.success("🎉 PREDICCIONES GENERADAS")
        logger.info("=" * 80)
        logger.info(f"\nPredicciones próximos {horizon_days} días:")
        for i, pred in enumerate(predictions, 1):
            logger.info(f"   Día +{i}: ${pred:.2f}")
        logger.info("")
        
        return {
            'model_id': model_id,
            'ticker': ticker,
            'horizon_days': horizon_days,
            'predictions': predictions,
            'prediction_date': datetime.now().date()
        }
    
    def _load_model(self, ticker: str, horizon_days: int, model_id: Optional[int]):
        """Cargar modelo (producción o específico)"""
        db_config = self.config['database']
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']}"
        )
        
        self.model_registry = ModelRegistry(
            conn_str=conn_str,
            models_path=self.config['paths']['models_dir']
        )
        
        if model_id:
            # Cargar modelo específico
            model, config = self.model_registry.load_model(model_id)
            return model, config, model_id
        else:
            # Cargar modelo en producción
            ticker_id = self._get_ticker_id(ticker)
            result = self.model_registry.get_production_model(ticker_id, horizon_days)
            
            if not result:
                raise ValueError(
                    f"No hay modelo en producción para {ticker}, horizon {horizon_days}"
                )
            
            return result
    
    def _load_recent_data(self, ticker: str):
        """Cargar datos recientes (últimos 6 meses)"""
        db_config = self.config['database']
        
        self.data_loader = OHLCVLoader(
            server=db_config['server'],
            database=db_config['database'],
            username=db_config['username'],
            password=db_config['password']
        )
        
        # Cargar últimos 6 meses
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=180)
        
        data = self.data_loader.load_data(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        return data
    
    def _add_features(self, data):
        """Feature engineering"""
        self.feature_engineer = FeatureEngineer()
        data_with_features = self.feature_engineer.add_all_features(data)
        data_with_features = data_with_features.dropna().reset_index(drop=True)
        return data_with_features
    
    def _create_last_sequence(self, data, config):
        """Crear última secuencia para predicción"""
        # Seleccionar features
        feature_cols = [col for col in data.columns if col not in ['fecha', 'ticker_id']]
        
        # Escalar
        self.scaler = DataScaler(method='minmax')
        X_scaled = self.scaler.fit_transform(data[feature_cols])
        
        # Crear sequence generator
        sequence_length = config.sequence_length
        
        self.sequence_generator = SequenceGenerator(
            sequence_length=sequence_length,
            horizon=1
        )
        
        # Obtener última secuencia
        last_sequence = self.sequence_generator.get_last_sequence(X_scaled)
        
        return last_sequence
    
    def _predict(self, model, last_sequence, horizon_days: int):
        """Generar predicciones"""
        predictions = []
        
        # Predecir iterativamente cada día
        current_sequence = last_sequence.copy()
        
        for day in range(horizon_days):
            # Predecir próximo día
            next_pred = model.predict(current_sequence[np.newaxis, :, :])[0]
            predictions.append(float(next_pred))
            
            # Actualizar secuencia (simplificado - en producción deberías actualizar todos los features)
            # Por ahora solo agregamos predicción al final
            current_sequence = np.roll(current_sequence, -1, axis=0)
            current_sequence[-1, 0] = next_pred  # Asumiendo que close es primera columna
        
        return predictions
    
    def _save_predictions(
        self,
        model_id: int,
        ticker_id: int,
        predictions: List[float],
        horizon_days: int
    ):
        """Guardar predicciones en base de datos"""
        db_config = self.config['database']
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']}"
        )
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            prediction_date = datetime.now().date()
            
            for days_ahead, predicted_close in enumerate(predictions, 1):
                target_date = prediction_date + timedelta(days=days_ahead)
                
                # Insertar o actualizar predicción
                query = """
                MERGE INTO ml.predictions AS target
                USING (VALUES (?, ?, ?, ?, ?)) AS source (model_id, ticker_id, prediction_date, target_date, days_ahead)
                ON target.model_id = source.model_id 
                   AND target.ticker_id = source.ticker_id
                   AND target.prediction_date = source.prediction_date
                   AND target.target_date = source.target_date
                WHEN MATCHED THEN
                    UPDATE SET predicted_close = ?
                WHEN NOT MATCHED THEN
                    INSERT (model_id, ticker_id, prediction_date, target_date, days_ahead, predicted_close)
                    VALUES (?, ?, ?, ?, ?, ?);
                """
                
                cursor.execute(query, (
                    model_id, ticker_id, prediction_date, target_date, days_ahead,
                    predicted_close,  # For UPDATE
                    model_id, ticker_id, prediction_date, target_date, days_ahead, predicted_close  # For INSERT
                ))
            
            conn.commit()
        
        logger.success(f"✅ {len(predictions)} predicciones guardadas")
    
    def _get_ticker_id(self, ticker: str) -> int:
        """Obtener ticker_id"""
        db_config = self.config['database']
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']}"
        )
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            if '.' in ticker:
                emisora, serie = ticker.split('.')
                query = "SELECT ticker_id FROM stage.cat_tickers WHERE emisora = ? AND serie = ?"
                cursor.execute(query, (emisora, serie))
            else:
                query = "SELECT ticker_id FROM stage.cat_tickers WHERE emisora = ?"
                cursor.execute(query, (ticker,))
            
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Ticker {ticker} no encontrado")
            
            return row[0]
