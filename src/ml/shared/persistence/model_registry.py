"""
Model Registry - Persistencia de modelos en base de datos
"""
import json
import pickle
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path
from loguru import logger
import pyodbc

from ..models.model_config import LSTMConfig


class ModelRegistry:
    """
    Registro de modelos en base de datos (ml.model_registry)
    
    Funcionalidades:
    - Guardar modelos entrenados con hyperparameters
    - Cargar modelos por ID
    - Obtener modelo en producción
    - Actualizar status de modelos
    - Registrar métricas de evaluación
    """
    
    def __init__(
        self,
        conn_str: str,
        models_path: str = "models/"
    ):
        """
        Args:
            conn_str: Connection string a SQL Server
            models_path: Directorio donde guardar archivos de modelos
        """
        self.conn_str = conn_str
        self.models_path = Path(models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
    
    def save_model(
        self,
        model,
        config: LSTMConfig,
        ticker_id: int,
        horizon_days: int,
        metrics: Dict,
        experiment_id: Optional[int] = None,
        status: str = 'TRAINED'
    ) -> int:
        """
        Guardar modelo en registro
        
        Args:
            model: Modelo LSTM entrenado
            config: Configuración del modelo
            ticker_id: ID del ticker
            horizon_days: Horizonte de predicción
            metrics: Dict con métricas de evaluación
            experiment_id: ID de experimento (si viene de GA)
            status: Estado del modelo (TRAINED, PRODUCTION, DEPRECATED)
            
        Returns:
            model_id: ID del modelo guardado
        """
        logger.info(f"💾 Guardando modelo en registro...")
        
        try:
            # Serializar hyperparámetros a JSON
            hyperparameters_json = json.dumps(config.to_dict())
            
            # Guardar archivo del modelo
            model_filename = f"lstm_ticker{ticker_id}_h{horizon_days}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.h5"
            model_path = self.models_path / model_filename
            
            model.save(str(model_path))
            
            # Insertar en base de datos
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                INSERT INTO ml.model_registry (
                    ticker_id,
                    horizon_days,
                    model_type,
                    hyperparameters,
                    model_path,
                    train_rmse,
                    train_mae,
                    val_rmse,
                    val_mae,
                    r2_score,
                    sharpe_ratio,
                    win_rate,
                    max_drawdown,
                    experiment_id,
                    status
                )
                OUTPUT INSERTED.model_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.execute(query, (
                    ticker_id,
                    horizon_days,
                    'LSTM',
                    hyperparameters_json,
                    str(model_path),
                    metrics.get('train_rmse'),
                    metrics.get('train_mae'),
                    metrics.get('val_rmse'),
                    metrics.get('val_mae'),
                    metrics.get('r2'),
                    metrics.get('sharpe_ratio'),
                    metrics.get('win_rate'),
                    metrics.get('max_drawdown'),
                    experiment_id,
                    status
                ))
                
                model_id = cursor.fetchone()[0]
                conn.commit()
            
            logger.success(f"✅ Modelo guardado con ID: {model_id}")
            logger.info(f"   Path: {model_path}")
            logger.info(f"   Val RMSE: {metrics.get('val_rmse', 'N/A'):.6f}")
            
            return model_id
            
        except Exception as e:
            logger.error(f"❌ Error guardando modelo: {e}")
            raise
    
    def load_model(self, model_id: int):
        """
        Cargar modelo por ID
        
        Args:
            model_id: ID del modelo
            
        Returns:
            (model, config): Tupla con modelo y configuración
        """
        logger.info(f"📂 Cargando modelo {model_id}...")
        
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT model_path, hyperparameters
                FROM ml.model_registry
                WHERE model_id = ?
                """
                
                cursor.execute(query, (model_id,))
                row = cursor.fetchone()
                
                if not row:
                    raise ValueError(f"Modelo {model_id} no encontrado")
                
                model_path, hyperparameters_json = row
            
            # Cargar modelo de archivo
            from tensorflow import keras
            model = keras.models.load_model(model_path)
            
            # Reconstruir config
            hyperparameters = json.loads(hyperparameters_json)
            config = LSTMConfig.from_dict(hyperparameters)
            
            logger.success(f"✅ Modelo {model_id} cargado")
            
            return model, config
            
        except Exception as e:
            logger.error(f"❌ Error cargando modelo: {e}")
            raise
    
    def get_production_model(
        self,
        ticker_id: int,
        horizon_days: int
    ) -> Optional[tuple]:
        """
        Obtener modelo en producción para ticker y horizonte
        
        Args:
            ticker_id: ID del ticker
            horizon_days: Horizonte de predicción
            
        Returns:
            (model_id, model, config) o None si no hay modelo en producción
        """
        logger.info(f"🔍 Buscando modelo en producción para ticker {ticker_id}, horizon {horizon_days}...")
        
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT model_id
                FROM ml.model_registry
                WHERE ticker_id = ?
                  AND horizon_days = ?
                  AND status = 'PRODUCTION'
                ORDER BY trained_at DESC
                """
                
                cursor.execute(query, (ticker_id, horizon_days))
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"⚠️  No hay modelo en producción")
                    return None
                
                model_id = row[0]
            
            # Cargar modelo
            model, config = self.load_model(model_id)
            
            return model_id, model, config
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo modelo en producción: {e}")
            return None
    
    def update_model_status(
        self,
        model_id: int,
        new_status: str
    ):
        """
        Actualizar status de modelo
        
        Args:
            model_id: ID del modelo
            new_status: Nuevo status (TRAINED, PRODUCTION, DEPRECATED)
        """
        logger.info(f"🔄 Actualizando modelo {model_id} a status {new_status}...")
        
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                UPDATE ml.model_registry
                SET status = ?
                WHERE model_id = ?
                """
                
                cursor.execute(query, (new_status, model_id))
                conn.commit()
            
            logger.success(f"✅ Modelo {model_id} actualizado a {new_status}")
            
        except Exception as e:
            logger.error(f"❌ Error actualizando status: {e}")
            raise
    
    def get_model_metrics(self, model_id: int) -> Dict:
        """
        Obtener métricas de un modelo
        
        Args:
            model_id: ID del modelo
            
        Returns:
            Dict con métricas
        """
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT train_rmse, train_mae, val_rmse, val_mae,
                       r2_score, sharpe_ratio, win_rate, max_drawdown
                FROM ml.model_registry
                WHERE model_id = ?
                """
                
                cursor.execute(query, (model_id,))
                row = cursor.fetchone()
                
                if not row:
                    return {}
                
                return {
                    'train_rmse': row[0],
                    'train_mae': row[1],
                    'val_rmse': row[2],
                    'val_mae': row[3],
                    'r2_score': row[4],
                    'sharpe_ratio': row[5],
                    'win_rate': row[6],
                    'max_drawdown': row[7]
                }
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo métricas: {e}")
            return {}
    
    def list_models(
        self,
        ticker_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Listar modelos con filtros
        
        Args:
            ticker_id: Filtrar por ticker (opcional)
            status: Filtrar por status (opcional)
            limit: Máximo de resultados
            
        Returns:
            Lista de dicts con info de modelos
        """
        try:
            with pyodbc.connect(self.conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT 
                    model_id,
                    ticker_id,
                    horizon_days,
                    val_rmse,
                    val_mae,
                    sharpe_ratio,
                    win_rate,
                    status,
                    trained_at
                FROM ml.model_registry
                WHERE 1=1
                """
                
                params = []
                
                if ticker_id:
                    query += " AND ticker_id = ?"
                    params.append(ticker_id)
                
                if status:
                    query += " AND status = ?"
                    params.append(status)
                
                query += " ORDER BY trained_at DESC"
                
                if limit:
                    query = f"SELECT TOP {limit} * FROM ({query}) t"
                
                cursor.execute(query, params)
                
                models = []
                for row in cursor.fetchall():
                    models.append({
                        'model_id': row[0],
                        'ticker_id': row[1],
                        'horizon_days': row[2],
                        'val_rmse': row[3],
                        'val_mae': row[4],
                        'sharpe_ratio': row[5],
                        'win_rate': row[6],
                        'status': row[7],
                        'trained_at': row[8]
                    })
                
                return models
                
        except Exception as e:
            logger.error(f"❌ Error listando modelos: {e}")
            return []
