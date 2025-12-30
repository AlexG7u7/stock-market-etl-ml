#!/usr/bin/env python3
"""
Script CLI para generar predicciones con modelo en producción

Uso:
    python src/ml/scripts/predict_next_days.py --ticker WALMEX --horizon 5
    python src/ml/scripts/predict_next_days.py --ticker ALSEA --horizon 10 --model-id 124
"""
import sys
import argparse
from pathlib import Path
from loguru import logger

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.pipelines.predict_pipeline import PredictionPipeline


def parse_args():
    """Parsear argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Generar predicciones para próximos días"
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
        "--model-id",
        type=int,
        default=None,
        help="ID del modelo a usar (si no se especifica, usa modelo en producción)"
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
    logger.info("🔮 PREDICT NEXT DAYS - CLI")
    logger.info("=" * 80)
    logger.info(f"Ticker: {args.ticker}")
    logger.info(f"Horizon: {args.horizon} días")
    
    if args.model_id:
        logger.info(f"Modelo ID: {args.model_id}")
    else:
        logger.info("Usando modelo en PRODUCCIÓN")
    
    logger.info("")
    
    try:
        # Crear pipeline de predicción
        pipeline = PredictionPipeline(config_path=args.config)
        
        # Generar predicciones
        result = pipeline.run(
            ticker=args.ticker,
            horizon_days=args.horizon,
            model_id=args.model_id
        )
        
        # Mostrar resultados
        logger.info("\n" + "=" * 80)
        logger.success("✅ PREDICCIONES GENERADAS")
        logger.info("=" * 80)
        logger.info(f"\nModelo usado: {result['model_id']}")
        logger.info(f"Fecha de predicción: {result['prediction_date']}")
        logger.info(f"\nPredicciones próximos {args.horizon} días:")
        
        for i, pred in enumerate(result['predictions'], 1):
            logger.info(f"   Día +{i}: ${pred:.2f}")
        
        logger.info("")
        logger.info("✅ Predicciones guardadas en ml.predictions")
        logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error generando predicciones: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
