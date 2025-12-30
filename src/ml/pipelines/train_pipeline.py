"""
Training Pipeline - Pipeline end-to-end para entrenar modelos LSTM
"""
import yaml
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
import numpy as np

from ..shared.data_loaders.ohlcv_loader import OHLCVLoader
from ..shared.data_loaders.feature_engineering import FeatureEngineer
from ..shared.preprocessors.scaler import DataScaler
from ..shared.preprocessors.sequence_generator import SequenceGenerator
from ..shared.preprocessors.train_test_splitter import TemporalSplitter
from ..shared.models.lstm_model import LSTMModel
from ..shared.models.model_config import LSTMConfig
from ..shared.evaluators.metrics import Metrics
from ..shared.persistence.model_registry import ModelRegistry


class TrainingPipeline:
    """
    Pipeline completo de entrenamiento:
    1. Cargar datos (OHLCV)
    2. Feature engineering
    3. Preprocesamiento (scaling, sequences)
    4. Split temporal (train/val/test)
    5. Entrenar modelo LSTM
    6. Evaluar en test set
    7. Guardar modelo en registry
    """
    
    def __init__(self, config_path: str = "src/ml/config/training_config.yml"):
        """
        Args:
            config_path: Path al archivo de configuración
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        self.data_loader = None
        self.feature_engineer = None
        self.scaler = None
        self.sequence_generator = None
        self.splitter = None
        self.model = None
        self.model_registry = None
    
    def _load_config(self) -> Dict:
        """Cargar configuración desde YAML"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def run(
        self,
        ticker: str,
        horizon_days: int = 5,
        lstm_config: Optional[LSTMConfig] = None,
        experiment_id: Optional[int] = None
    ) -> Dict:
        """
        Ejecutar pipeline completo de entrenamiento
        
        Args:
            ticker: Símbolo del ticker (ej: 'WALMEX')
            horizon_days: Días a predecir (5, 10, 15)
            lstm_config: Configuración del LSTM (opcional, usa default si no se proporciona)
            experiment_id: ID de experimento si viene de GA (opcional)
            
        Returns:
            Dict con resultados del entrenamiento
        """
        logger.info("=" * 80)
        logger.info("🚀 TRAINING PIPELINE - INICIO")
        logger.info("=" * 80)
        logger.info(f"Ticker: {ticker}")
        logger.info(f"Horizon: {horizon_days} días")
        logger.info("")
        
        # 1. Cargar datos
        logger.info("📊 PASO 1: Cargar datos...")
        data = self._load_data(ticker)
        logger.success(f"✅ Datos cargados: {len(data)} registros")
        
        # 2. Feature engineering
        logger.info("\n🔧 PASO 2: Feature engineering...")
        data_with_features = self._add_features(data)
        logger.success(f"✅ Features creados: {len(data_with_features.columns)} columnas")
        
        # 3. Preprocesar
        logger.info("\n⚙️  PASO 3: Preprocesamiento...")
        X_scaled, y_scaled, feature_names = self._preprocess(data_with_features, horizon_days)
        logger.success(f"✅ Datos escalados: {X_scaled.shape}")
        
        # 4. Split temporal
        logger.info("\n✂️  PASO 4: Split temporal...")
        splits = self._split_data(X_scaled, y_scaled)
        logger.success(
            f"✅ Train: {splits['X_train'].shape[0]}, "
            f"Val: {splits['X_val'].shape[0]}, "
            f"Test: {splits['X_test'].shape[0]}"
        )
        
        # 5. Crear y entrenar modelo
        logger.info("\n🧠 PASO 5: Entrenar modelo LSTM...")
        
        if lstm_config is None:
            # Usar configuración por defecto
            lstm_config = LSTMConfig()
        
        self.model = LSTMModel(lstm_config)
        self.model.build(
            sequence_length=splits['X_train'].shape[1],
            num_features=splits['X_train'].shape[2]
        )
        
        history = self.model.train(
            X_train=splits['X_train'],
            y_train=splits['y_train'],
            X_val=splits['X_val'],
            y_val=splits['y_val']
        )
        
        logger.success("✅ Entrenamiento completado")
        
        # 6. Evaluar
        logger.info("\n📈 PASO 6: Evaluación...")
        metrics = self._evaluate(splits)
        
        Metrics.print_metrics(metrics)
        
        # 7. Guardar modelo
        logger.info("\n💾 PASO 7: Guardar modelo...")
        model_id = self._save_model(
            ticker=ticker,
            horizon_days=horizon_days,
            config=lstm_config,
            metrics=metrics,
            experiment_id=experiment_id
        )
        
        logger.info("\n" + "=" * 80)
        logger.success(f"🎉 PIPELINE COMPLETADO - Modelo ID: {model_id}")
        logger.info("=" * 80)
        
        return {
            'model_id': model_id,
            'metrics': metrics,
            'history': history.history,
            'config': lstm_config.to_dict()
        }
    
    def _load_data(self, ticker: str):
        """Cargar datos desde base de datos"""
        db_config = self.config['database']
        
        self.data_loader = OHLCVLoader(
            server=db_config['server'],
            database=db_config['database'],
            username=db_config['username'],
            password=db_config['password']
        )
        
        data = self.data_loader.load_data(ticker=ticker)
        return data
    
    def _add_features(self, data):
        """Agregar features técnicos"""
        self.feature_engineer = FeatureEngineer()
        
        data_with_features = self.feature_engineer.add_all_features(data)
        
        # Remover NaN de indicadores
        data_with_features = data_with_features.dropna().reset_index(drop=True)
        
        return data_with_features
    
    def _preprocess(self, data, horizon_days: int):
        """Escalar datos y crear secuencias"""
        # Seleccionar features
        feature_cols = [col for col in data.columns if col not in ['fecha', 'ticker_id']]
        target_col = 'close'
        
        # Escalar
        self.scaler = DataScaler(method='minmax')
        X_scaled = self.scaler.fit_transform(data[feature_cols])
        
        # Target (solo close)
        y = data[target_col].values
        
        # Crear secuencias
        sequence_length = self.config.get('sequence_length', 60)
        
        self.sequence_generator = SequenceGenerator(
            sequence_length=sequence_length,
            horizon=horizon_days
        )
        
        X_sequences, y_sequences = self.sequence_generator.create_sequences(
            X_scaled,
            y
        )
        
        return X_sequences, y_sequences, feature_cols
    
    def _split_data(self, X, y):
        """Split temporal"""
        self.splitter = TemporalSplitter(
            test_size=90,  # 3 meses
            val_size=60    # 2 meses
        )
        
        splits = self.splitter.split_arrays(X, y)
        
        return splits
    
    def _evaluate(self, splits) -> Dict:
        """Evaluar modelo en todos los sets"""
        metrics = {}
        
        # Train
        y_train_pred = self.model.predict(splits['X_train'])
        train_metrics = Metrics.calculate_all_metrics(
            y_true=splits['y_train'],
            y_pred=y_train_pred
        )
        metrics.update({f'train_{k}': v for k, v in train_metrics.items()})
        
        # Validation
        y_val_pred = self.model.predict(splits['X_val'])
        val_metrics = Metrics.calculate_all_metrics(
            y_true=splits['y_val'],
            y_pred=y_val_pred
        )
        metrics.update({f'val_{k}': v for k, v in val_metrics.items()})
        
        # Test
        y_test_pred = self.model.predict(splits['X_test'])
        test_metrics = Metrics.calculate_all_metrics(
            y_true=splits['y_test'],
            y_pred=y_test_pred
        )
        metrics.update({f'test_{k}': v for k, v in test_metrics.items()})
        
        return metrics
    
    def _save_model(
        self,
        ticker: str,
        horizon_days: int,
        config: LSTMConfig,
        metrics: Dict,
        experiment_id: Optional[int]
    ) -> int:
        """Guardar modelo en registry"""
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
        
        # Obtener ticker_id
        ticker_id = self._get_ticker_id(ticker)
        
        model_id = self.model_registry.save_model(
            model=self.model.model,
            config=config,
            ticker_id=ticker_id,
            horizon_days=horizon_days,
            metrics=metrics,
            experiment_id=experiment_id,
            status='TRAINED'
        )
        
        return model_id
    
    def _get_ticker_id(self, ticker: str) -> int:
        """Obtener ticker_id desde base de datos"""
        import pyodbc
        
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
            
            # Separar emisora y serie
            if '.' in ticker:
                emisora, serie = ticker.split('.')
            else:
                emisora = ticker
                serie = None
            
            if serie:
                query = """
                SELECT ticker_id 
                FROM stage.cat_tickers 
                WHERE emisora = ? AND serie = ?
                """
                cursor.execute(query, (emisora, serie))
            else:
                query = """
                SELECT ticker_id 
                FROM stage.cat_tickers 
                WHERE emisora = ?
                """
                cursor.execute(query, (emisora,))
            
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Ticker {ticker} no encontrado")
            
            return row[0]
