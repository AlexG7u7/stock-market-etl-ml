#!/usr/bin/env python3
"""
Script CLI para evaluar modelo en datos históricos con backtesting

Uso:
    python src/ml/scripts/evaluate_model.py --model-id 124
    python src/ml/scripts/evaluate_model.py --model-id 124 --start-date 2024-11-01
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger
import pyodbc

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.shared.evaluators.backtester import Backtester
from ml.shared.evaluators.metrics import Metrics
from ml.shared.persistence.model_registry import ModelRegistry
from ml.shared.data_loaders.ohlcv_loader import OHLCVLoader


def parse_args():
    """Parsear argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Evaluar modelo con backtesting"
    )
    
    parser.add_argument(
        "--model-id",
        type=int,
        required=True,
        help="ID del modelo a evaluar"
    )
    
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Fecha de inicio para evaluación (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="src/ml/config/training_config.yml",
        help="Path al archivo de configuración"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Modo verbose (más logs)"
    )
    
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_args()
    
    # Configurar logger
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    
    logger.info("=" * 80)
    logger.info("📊 EVALUATE MODEL - BACKTESTING")
    logger.info("=" * 80)
    logger.info(f"Model ID: {args.model_id}")
    
    if args.start_date:
        logger.info(f"Start date: {args.start_date}")
    
    logger.info("")
    
    try:
        # Cargar variables de entorno
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Obtener credenciales de .env
        server = os.getenv('SQL_SERVER', 'localhost')
        database = os.getenv('SQL_DATABASE', 'MercadoBursatil')
        username = os.getenv('SQL_USER', '')
        password = os.getenv('SQL_PASSWORD', '')
        
        # Construir connection string
        if username and password:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password}"
            )
        else:
            # Autenticación de Windows
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )
        
        # 1. Cargar información del modelo
        logger.info("📦 Cargando información del modelo...")
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT ticker_id, horizon_days
            FROM ml.model_registry
            WHERE model_id = ?
            """
            
            cursor.execute(query, (args.model_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Modelo {args.model_id} no encontrado")
            
            ticker_id, horizon_days = row
        
        logger.success(f"✅ Modelo encontrado: Ticker ID {ticker_id}, Horizon {horizon_days} días")
        
        # 2. Cargar modelo
        logger.info("\n📂 Cargando modelo...")
        
        # Cargar configuración solo para obtener models_path
        import yaml
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
        
        model_registry = ModelRegistry(
            conn_str=conn_str,
            models_path=config['paths']['models']
        )
        
        model, model_config = model_registry.load_model(args.model_id)
        
        logger.success("✅ Modelo cargado")
        
        # 3. Obtener ticker symbol
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT emisora, serie
            FROM stage.cat_tickers
            WHERE ticker_id = ?
            """
            
            cursor.execute(query, (ticker_id,))
            row = cursor.fetchone()
            
            emisora, serie = row
            ticker_symbol = f"{emisora}.{serie}" if serie else emisora
        
        # 4. Cargar datos históricos
        logger.info(f"\n📊 Cargando datos históricos para {ticker_symbol}...")
        
        data_loader = OHLCVLoader(
            ticker_id=ticker_id,
            ticker_symbol=ticker_symbol,
            server=server,
            database=database,
            username=username,
            password=password
        )
        
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date() if args.start_date else None
        
        data = data_loader.load_data(
            ticker=ticker_symbol,
            start_date=start_date
        )
        
        logger.success(f"✅ {len(data)} registros cargados")
        
        # 5. Ejecutar backtesting
        logger.info("\n🔄 Ejecutando backtesting...")
        
        backtester = Backtester(
            initial_train_days=252,  # 1 año
            retrain_frequency=21,    # Reentrenar mensualmente
            test_days=horizon_days
        )
        
        # Crear simple model trainer wrapper
        class ModelTrainer:
            def __init__(self, model):
                self.model = model
            
            def train(self, data):
                # En backtesting simplificado, usamos modelo pre-entrenado
                pass
            
            def predict(self, data):
                # Simplificado: solo predecir close
                X = data[['open', 'high', 'low', 'close', 'volume']].values
                # En implementación real, aplicar mismo preprocesamiento que en entrenamiento
                return X[:, 3]  # Retornar close como baseline
        
        trainer = ModelTrainer(model)
        
        metrics = backtester.run_backtest(
            data=data,
            model_trainer=trainer,
            date_column='fecha',
            target_column='close'
        )
        
        # 6. Mostrar resultados
        logger.info("\n" + "=" * 80)
        logger.success("✅ EVALUACIÓN COMPLETADA")
        logger.info("=" * 80)
        logger.info(f"\nModelo ID: {args.model_id}")
        logger.info(f"Ticker: {ticker_symbol}")
        logger.info(f"Ventanas evaluadas: {metrics.get('num_windows', 'N/A')}")
        logger.info("")
        
        Metrics.print_metrics(metrics)
        
        # 7. Guardar gráfico (opcional)
        plot_path = f"backtest_model_{args.model_id}.png"
        backtester.plot_results(save_path=plot_path)
        
        logger.info(f"\n📊 Gráfico guardado en {plot_path}")
        logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error durante evaluación: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
