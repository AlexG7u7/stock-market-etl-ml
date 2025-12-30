#!/usr/bin/env python3
"""
Script CLI para deployment de modelo con A/B Testing

Uso:
    python src/ml/scripts/deploy_model.py --current-model-id 120 --challenger-id 124
    python src/ml/scripts/deploy_model.py --current-model-id 120 --challenger-id 124 --test-days 45
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
import pyodbc
import numpy as np

# Agregar src/ al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.shared.evaluators.ab_tester import ABTester
from ml.shared.persistence.model_registry import ModelRegistry


def parse_args():
    """Parsear argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Deployment de modelo con A/B Testing"
    )
    
    parser.add_argument(
        "--current-model-id",
        type=int,
        required=True,
        help="ID del modelo actualmente en producción"
    )
    
    parser.add_argument(
        "--challenger-id",
        type=int,
        required=True,
        help="ID del modelo challenger (candidato a producción)"
    )
    
    parser.add_argument(
        "--test-days",
        type=int,
        default=30,
        help="Días de test para comparación (default: 30)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="src/ml/config/training_config.yml",
        help="Path al archivo de configuración"
    )
    
    parser.add_argument(
        "--auto-deploy",
        action="store_true",
        help="Deployment automático si pasa criterios (default: requiere confirmación manual)"
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
    logger.info("🚀 DEPLOY MODEL - A/B TESTING")
    logger.info("=" * 80)
    logger.info(f"Modelo actual (A): {args.current_model_id}")
    logger.info(f"Modelo challenger (B): {args.challenger_id}")
    logger.info(f"Días de test: {args.test_days}")
    logger.info("")
    
    try:
        # Cargar configuración
        import yaml
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
        
        db_config = config['database']
        
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']}"
        )
        
        # 1. Validar que ambos modelos existen y son del mismo ticker/horizon
        logger.info("🔍 Validando modelos...")
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT ticker_id, horizon_days, status
            FROM ml.model_registry
            WHERE model_id IN (?, ?)
            """
            
            cursor.execute(query, (args.current_model_id, args.challenger_id))
            rows = cursor.fetchall()
            
            if len(rows) != 2:
                raise ValueError("Uno o ambos modelos no encontrados")
            
            # Validar que sean del mismo ticker y horizon
            ticker_ids = {row[0] for row in rows}
            horizons = {row[1] for row in rows}
            
            if len(ticker_ids) != 1 or len(horizons) != 1:
                raise ValueError("Los modelos deben ser del mismo ticker y horizonte")
            
            ticker_id = list(ticker_ids)[0]
            horizon_days = list(horizons)[0]
        
        logger.success(f"✅ Modelos válidos: Ticker ID {ticker_id}, Horizon {horizon_days} días")
        
        # 2. Obtener predicciones de ambos modelos en últimos N días
        logger.info(f"\n📊 Obteniendo predicciones de últimos {args.test_days} días...")
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.test_days)
        
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            
            # Predicciones de modelo A
            query = """
            SELECT p.target_date, p.predicted_close, p.actual_close
            FROM ml.predictions p
            WHERE p.model_id = ?
              AND p.ticker_id = ?
              AND p.prediction_date >= ?
              AND p.prediction_date <= ?
              AND p.actual_close IS NOT NULL
            ORDER BY p.target_date
            """
            
            cursor.execute(query, (args.current_model_id, ticker_id, start_date, end_date))
            predictions_a = cursor.fetchall()
            
            # Predicciones de modelo B
            cursor.execute(query, (args.challenger_id, ticker_id, start_date, end_date))
            predictions_b = cursor.fetchall()
        
        if not predictions_a or not predictions_b:
            raise ValueError(
                f"Insuficientes predicciones para comparación. "
                f"Modelo A: {len(predictions_a)}, Modelo B: {len(predictions_b)}"
            )
        
        # Convertir a arrays
        dates_a = [p[0] for p in predictions_a]
        preds_a = np.array([p[1] for p in predictions_a])
        actuals_a = np.array([p[2] for p in predictions_a])
        
        dates_b = [p[0] for p in predictions_b]
        preds_b = np.array([p[1] for p in predictions_b])
        actuals_b = np.array([p[2] for p in predictions_b])
        
        # Alinear por fechas comunes
        common_dates = set(dates_a).intersection(set(dates_b))
        
        if len(common_dates) < 10:
            raise ValueError(
                f"Solo {len(common_dates)} fechas comunes. Se necesitan al menos 10 para comparación válida."
            )
        
        logger.success(f"✅ {len(common_dates)} fechas comunes encontradas")
        
        # 3. Ejecutar A/B Test
        logger.info("\n🔬 Ejecutando A/B Testing...")
        
        ab_tester = ABTester(
            min_test_days=args.test_days,
            improvement_threshold={
                'rmse': 0.05,
                'mae': 0.05,
                'win_rate': 0.02,
                'sharpe_ratio': 0.10
            },
            significance_level=0.05
        )
        
        results = ab_tester.compare_models(
            model_a_predictions=preds_a,
            model_b_predictions=preds_b,
            actuals=actuals_a,
            model_a_name=f"Modelo {args.current_model_id} (Producción)",
            model_b_name=f"Modelo {args.challenger_id} (Challenger)"
        )
        
        # 4. Decisión de deployment
        should_deploy = ab_tester.should_deploy()
        winner = ab_tester.get_winner()
        
        logger.info("\n" + "=" * 80)
        
        if should_deploy:
            logger.success("🚀 RECOMENDACIÓN: DESPLEGAR MODELO CHALLENGER")
            logger.info("=" * 80)
            logger.info("\nEl modelo challenger supera al modelo actual:")
            for reason in results['decision']['reasons']:
                logger.info(f"   {reason}")
            
            # Confirmar deployment (si no es auto)
            if not args.auto_deploy:
                logger.info("")
                response = input("¿Confirmar deployment? (yes/no): ")
                
                if response.lower() not in ['yes', 'y', 'si', 's']:
                    logger.warning("⏸️  Deployment cancelado por usuario")
                    return 0
            
            # Ejecutar deployment
            logger.info("\n🚀 Ejecutando deployment...")
            
            model_registry = ModelRegistry(
                conn_str=conn_str,
                models_path=config['paths']['models_dir']
            )
            
            # Cambiar status: Actual a DEPRECATED, Challenger a PRODUCTION
            model_registry.update_model_status(args.current_model_id, 'DEPRECATED')
            model_registry.update_model_status(args.challenger_id, 'PRODUCTION')
            
            # Registrar A/B test en base de datos
            with pyodbc.connect(conn_str) as conn:
                cursor = conn.cursor()
                
                query = """
                INSERT INTO ml.ab_tests (
                    model_a_id,
                    model_b_id,
                    ticker_id,
                    test_start_date,
                    test_end_date,
                    model_a_rmse,
                    model_b_rmse,
                    model_a_mae,
                    model_b_mae,
                    model_a_win_rate,
                    model_b_win_rate,
                    winner,
                    deployed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.execute(query, (
                    args.current_model_id,
                    args.challenger_id,
                    ticker_id,
                    start_date,
                    end_date,
                    results['metrics_a']['rmse'],
                    results['metrics_b']['rmse'],
                    results['metrics_a']['mae'],
                    results['metrics_b']['mae'],
                    results['metrics_a'].get('win_rate'),
                    results['metrics_b'].get('win_rate'),
                    winner,
                    True
                ))
                
                conn.commit()
            
            logger.success(f"\n✅ Modelo {args.challenger_id} desplegado a PRODUCCIÓN")
            logger.info(f"   Modelo {args.current_model_id} marcado como DEPRECATED")
            logger.info("")
            
        else:
            logger.warning("⏸️  RECOMENDACIÓN: MANTENER MODELO ACTUAL")
            logger.info("=" * 80)
            logger.info("\nEl modelo challenger NO supera suficientemente al actual:")
            for reason in results['decision']['reasons']:
                logger.info(f"   {reason}")
            logger.info("")
            logger.info("💡 Sugerencias:")
            logger.info("   - Continuar optimizando hyperparámetros")
            logger.info("   - Agregar más features")
            logger.info("   - Aumentar datos de entrenamiento")
            logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error durante deployment: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
