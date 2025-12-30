#!/usr/bin/env python3
"""
Script CLI para optimizar hyperparámetros con Genetic Algorithm

Uso:
    python src/ml/scripts/optimize_hyperparams.py --ticker WALMEX --horizon 5
    python src/ml/scripts/optimize_hyperparams.py --ticker ALSEA --horizon 10 --population 30 --generations 15
"""
import sys
import argparse
from pathlib import Path
from loguru import logger

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.pipelines.optimization_pipeline import OptimizationPipeline


def parse_args():
    """Parsear argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Optimizar hyperparámetros de LSTM con Genetic Algorithm"
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
        "--population",
        type=int,
        default=None,
        help="Tamaño de población (default: 20)"
    )
    
    parser.add_argument(
        "--generations",
        type=int,
        default=None,
        help="Número de generaciones (default: 10)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="src/ml/config/lstm_search_space.yml",
        help="Path al archivo de configuración de GA"
    )
    
    parser.add_argument(
        "--training-config",
        type=str,
        default="src/ml/config/training_config.yml",
        help="Path al archivo de configuración de training"
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
    logger.info("🧬 OPTIMIZE HYPERPARAMETERS - GENETIC ALGORITHM")
    logger.info("=" * 80)
    logger.info(f"Ticker: {args.ticker}")
    logger.info(f"Horizon: {args.horizon} días")
    
    if args.population:
        logger.info(f"Population size: {args.population}")
    if args.generations:
        logger.info(f"Generations: {args.generations}")
    
    logger.info("")
    logger.warning("⚠️  Este proceso puede tomar varias horas...")
    logger.info("    (Depende del tamaño de población y generaciones)")
    logger.info("")
    
    try:
        # Crear pipeline de optimización
        pipeline = OptimizationPipeline(
            config_path=args.config,
            training_config_path=args.training_config
        )
        
        # Ejecutar optimización
        result = pipeline.run(
            ticker=args.ticker,
            horizon_days=args.horizon,
            population_size=args.population,
            num_generations=args.generations
        )
        
        # Mostrar resultados
        logger.info("\n" + "=" * 80)
        logger.success("🎉 OPTIMIZACIÓN COMPLETADA")
        logger.info("=" * 80)
        logger.info(f"\nExperimento ID: {result['experiment_id']}")
        logger.info(f"Mejor modelo ID: {result['best_model_id']}")
        logger.info(f"Mejor fitness: {result['best_fitness']:.6f}")
        
        logger.info(f"\nMejores hyperparámetros encontrados:")
        for param, value in result['best_hyperparameters'].items():
            logger.info(f"   {param}: {value}")
        
        logger.info(f"\nMétricas del mejor modelo:")
        metrics = result['final_metrics']
        logger.info(f"   Val RMSE: {metrics.get('val_rmse', 'N/A'):.6f}")
        logger.info(f"   Val MAE: {metrics.get('val_mae', 'N/A'):.6f}")
        logger.info(f"   Val R²: {metrics.get('val_r2', 'N/A'):.6f}")
        logger.info(f"   Win Rate: {metrics.get('val_win_rate', 'N/A')*100:.2f}%")
        logger.info(f"   Sharpe Ratio: {metrics.get('val_sharpe_ratio', 'N/A'):.6f}")
        logger.info("")
        
        logger.info("Siguiente paso:")
        logger.info(f"   python src/ml/scripts/evaluate_model.py --model-id {result['best_model_id']}")
        logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error durante optimización: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
