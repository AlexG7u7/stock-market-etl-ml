#!/usr/bin/env python3
"""
Script CLI para entrenar un modelo LSTM

Uso:
    python src/ml/scripts/train_model.py --ticker WALMEX --horizon 5
    python src/ml/scripts/train_model.py --ticker ALSEA --horizon 10 --config custom_config.yml
"""
import sys
import argparse
from pathlib import Path
from loguru import logger

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.pipelines.train_pipeline import TrainingPipeline
from ml.shared.models.model_config import LSTMConfig


def parse_args():
    """Parsear argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Entrenar modelo LSTM para predicción de precios"
    )
    
    parser.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Símbolo del ticker (ej: WALMEX, ALSEA)"
    )
    
    parser.add_argument(
        "--horizon",
        type=int,
        default=5,
        choices=[5, 10, 15],
        help="Horizonte de predicción en días (5, 10 o 15)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="src/ml/config/training_config.yml",
        help="Path al archivo de configuración"
    )
    
    parser.add_argument(
        "--sequence-length",
        type=int,
        default=60,
        help="Longitud de secuencia de entrada (días históricos)"
    )
    
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Número de capas LSTM"
    )
    
    parser.add_argument(
        "--hidden-units",
        type=int,
        default=128,
        help="Unidades ocultas por capa"
    )
    
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.2,
        help="Tasa de dropout"
    )
    
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.001,
        help="Learning rate"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size"
    )
    
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Número máximo de epochs"
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
    logger.info("🚀 TRAIN MODEL - CLI")
    logger.info("=" * 80)
    logger.info(f"Ticker: {args.ticker}")
    logger.info(f"Horizon: {args.horizon} días")
    logger.info("")
    
    try:
        # Crear configuración LSTM
        lstm_config = LSTMConfig(
            sequence_length=args.sequence_length,
            num_layers=args.num_layers,
            hidden_units=args.hidden_units,
            dropout_rate=args.dropout,
            learning_rate=args.learning_rate,
            batch_size=args.batch_size,
            epochs=args.epochs
        )
        
        logger.info("Configuración LSTM:")
        logger.info(f"   Sequence length: {lstm_config.sequence_length}")
        logger.info(f"   Layers: {lstm_config.num_layers}")
        logger.info(f"   Hidden units: {lstm_config.hidden_units}")
        logger.info(f"   Dropout: {lstm_config.dropout_rate}")
        logger.info(f"   Learning rate: {lstm_config.learning_rate}")
        logger.info(f"   Batch size: {lstm_config.batch_size}")
        logger.info(f"   Max epochs: {lstm_config.epochs}")
        logger.info("")
        
        # Crear pipeline de entrenamiento
        pipeline = TrainingPipeline(config_path=args.config)
        
        # Entrenar modelo
        result = pipeline.run(
            ticker=args.ticker,
            horizon_days=args.horizon,
            lstm_config=lstm_config
        )
        
        # Mostrar resultados
        logger.info("\n" + "=" * 80)
        logger.success("✅ ENTRENAMIENTO EXITOSO")
        logger.info("=" * 80)
        logger.info(f"\nModelo ID: {result['model_id']}")
        logger.info(f"\nMétricas de validación:")
        logger.info(f"   RMSE: {result['metrics'].get('val_rmse', 'N/A'):.6f}")
        logger.info(f"   MAE: {result['metrics'].get('val_mae', 'N/A'):.6f}")
        logger.info(f"   R²: {result['metrics'].get('val_r2', 'N/A'):.6f}")
        logger.info(f"   Win Rate: {result['metrics'].get('val_win_rate', 'N/A')*100:.2f}%")
        logger.info("")
        
        logger.info("Siguiente paso:")
        logger.info(f"   python src/ml/scripts/evaluate_model.py --model-id {result['model_id']}")
        logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error durante entrenamiento: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
