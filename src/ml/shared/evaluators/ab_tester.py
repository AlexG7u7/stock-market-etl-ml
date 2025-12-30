"""
A/B Tester - Comparación estadística de modelos para deployment
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from scipy import stats
from loguru import logger

from .metrics import Metrics


class ABTester:
    """
    A/B Testing para comparar modelo en producción (A) vs nuevo modelo (B)
    
    Proceso:
    1. Ejecutar ambos modelos en paralelo por N días
    2. Comparar métricas (RMSE, MAE, Win Rate, Sharpe)
    3. Calcular significancia estadística
    4. Decidir si hacer deployment del nuevo modelo
    
    Criterios de deployment:
    - Nuevo modelo debe ser X% mejor
    - Mejora debe ser estadísticamente significativa
    - No debe empeorar métricas críticas
    """
    
    def __init__(
        self,
        min_test_days: int = 30,
        improvement_threshold: Dict[str, float] = None,
        significance_level: float = 0.05
    ):
        """
        Args:
            min_test_days: Mínimo de días para test válido
            improvement_threshold: % de mejora requerida por métrica
            significance_level: Nivel de significancia para pruebas (default 5%)
        """
        self.min_test_days = min_test_days
        self.significance_level = significance_level
        
        # Umbrales de mejora por defecto
        self.improvement_threshold = improvement_threshold or {
            'rmse': 0.05,        # 5% mejor
            'mae': 0.05,         # 5% mejor
            'win_rate': 0.02,    # 2% mejor (absoluto)
            'sharpe_ratio': 0.10 # 10% mejor
        }
        
        self.results: Dict = {}
    
    def compare_models(
        self,
        model_a_predictions: np.ndarray,
        model_b_predictions: np.ndarray,
        actuals: np.ndarray,
        model_a_name: str = "Modelo A (Producción)",
        model_b_name: str = "Modelo B (Challenger)"
    ) -> Dict:
        """
        Comparar dos modelos
        
        Args:
            model_a_predictions: Predicciones del modelo actual
            model_b_predictions: Predicciones del modelo nuevo
            actuals: Valores reales
            model_a_name: Nombre del modelo A
            model_b_name: Nombre del modelo B
            
        Returns:
            Dict con resultados de comparación
        """
        logger.info("🔬 A/B TESTING - COMPARACIÓN DE MODELOS")
        logger.info("=" * 80)
        logger.info(f"Modelo A: {model_a_name}")
        logger.info(f"Modelo B: {model_b_name}")
        logger.info(f"Días de test: {len(actuals)}")
        logger.info("")
        
        # Validar datos
        if len(actuals) < self.min_test_days:
            logger.warning(f"⚠️  Solo {len(actuals)} días, se requieren mínimo {self.min_test_days}")
        
        # Calcular métricas para cada modelo
        metrics_a = Metrics.calculate_all_metrics(actuals, model_a_predictions)
        metrics_b = Metrics.calculate_all_metrics(actuals, model_b_predictions)
        
        # Comparar métricas
        logger.info("📊 MÉTRICAS COMPARATIVAS")
        logger.info("=" * 80)
        
        comparison = {}
        
        for metric in ['rmse', 'mae', 'win_rate', 'sharpe_ratio', 'r2']:
            if metric in metrics_a and metric in metrics_b:
                value_a = metrics_a[metric]
                value_b = metrics_b[metric]
                
                # Calcular diferencia
                if metric in ['rmse', 'mae']:
                    # Menor es mejor
                    improvement = (value_a - value_b) / value_a
                    better = 'B' if value_b < value_a else 'A'
                else:
                    # Mayor es mejor
                    improvement = (value_b - value_a) / abs(value_a) if value_a != 0 else 0
                    better = 'B' if value_b > value_a else 'A'
                
                comparison[metric] = {
                    'model_a': value_a,
                    'model_b': value_b,
                    'improvement_pct': improvement * 100,
                    'better': better
                }
                
                logger.info(f"\n{metric.upper()}:")
                logger.info(f"   Modelo A: {value_a:.6f}")
                logger.info(f"   Modelo B: {value_b:.6f}")
                logger.info(f"   {'Mejora' if improvement > 0 else 'Empeora'}: {abs(improvement)*100:.2f}%")
                logger.info(f"   Ganador: Modelo {better}")
        
        # Pruebas de significancia estadística
        logger.info("\n" + "=" * 80)
        logger.info("📈 SIGNIFICANCIA ESTADÍSTICA")
        logger.info("=" * 80)
        
        statistical_tests = self._run_statistical_tests(
            model_a_predictions,
            model_b_predictions,
            actuals
        )
        
        # Decisión de deployment
        logger.info("\n" + "=" * 80)
        logger.info("🚀 DECISIÓN DE DEPLOYMENT")
        logger.info("=" * 80)
        
        decision = self._make_deployment_decision(comparison, statistical_tests)
        
        # Guardar resultados
        self.results = {
            'model_a_name': model_a_name,
            'model_b_name': model_b_name,
            'test_days': len(actuals),
            'metrics_a': metrics_a,
            'metrics_b': metrics_b,
            'comparison': comparison,
            'statistical_tests': statistical_tests,
            'decision': decision
        }
        
        return self.results
    
    def _run_statistical_tests(
        self,
        preds_a: np.ndarray,
        preds_b: np.ndarray,
        actuals: np.ndarray
    ) -> Dict:
        """
        Ejecutar pruebas estadísticas de significancia
        
        Returns:
            Dict con resultados de pruebas
        """
        results = {}
        
        # Calcular errores
        errors_a = np.abs(actuals - preds_a)
        errors_b = np.abs(actuals - preds_b)
        
        # Paired t-test (errores)
        t_stat, p_value = stats.ttest_rel(errors_a, errors_b)
        
        results['paired_t_test'] = {
            't_statistic': t_stat,
            'p_value': p_value,
            'significant': p_value < self.significance_level,
            'better_model': 'B' if t_stat > 0 else 'A'
        }
        
        logger.info(f"Paired t-test (errores):")
        logger.info(f"   t-statistic: {t_stat:.4f}")
        logger.info(f"   p-value: {p_value:.4f}")
        logger.info(f"   {'✅ Significativo' if p_value < self.significance_level else '❌ No significativo'}")
        
        # Wilcoxon signed-rank test (no paramétrico)
        w_stat, w_pvalue = stats.wilcoxon(errors_a, errors_b)
        
        results['wilcoxon_test'] = {
            'w_statistic': w_stat,
            'p_value': w_pvalue,
            'significant': w_pvalue < self.significance_level
        }
        
        logger.info(f"\nWilcoxon signed-rank test:")
        logger.info(f"   W-statistic: {w_stat:.4f}")
        logger.info(f"   p-value: {w_pvalue:.4f}")
        logger.info(f"   {'✅ Significativo' if w_pvalue < self.significance_level else '❌ No significativo'}")
        
        return results
    
    def _make_deployment_decision(
        self,
        comparison: Dict,
        statistical_tests: Dict
    ) -> Dict:
        """
        Decidir si hacer deployment del nuevo modelo
        
        Args:
            comparison: Comparación de métricas
            statistical_tests: Resultados de pruebas estadísticas
            
        Returns:
            Dict con decisión y razones
        """
        reasons = []
        deploy = True
        
        # Revisar umbral de mejora para métricas críticas
        for metric, threshold in self.improvement_threshold.items():
            if metric in comparison:
                improvement = comparison[metric]['improvement_pct'] / 100
                
                if metric in ['rmse', 'mae']:
                    # Menor es mejor (improvement positivo significa B es mejor)
                    if improvement < threshold:
                        deploy = False
                        reasons.append(
                            f"❌ {metric.upper()} mejora {improvement*100:.2f}% "
                            f"(requiere {threshold*100:.1f}%)"
                        )
                    else:
                        reasons.append(
                            f"✅ {metric.upper()} mejora {improvement*100:.2f}% "
                            f"(requiere {threshold*100:.1f}%)"
                        )
                else:
                    # Mayor es mejor
                    if improvement < threshold:
                        deploy = False
                        reasons.append(
                            f"❌ {metric.upper()} mejora {improvement*100:.2f}% "
                            f"(requiere {threshold*100:.1f}%)"
                        )
                    else:
                        reasons.append(
                            f"✅ {metric.upper()} mejora {improvement*100:.2f}% "
                            f"(requiere {threshold*100:.1f}%)"
                        )
        
        # Revisar significancia estadística
        if not statistical_tests['paired_t_test']['significant']:
            deploy = False
            reasons.append(
                f"❌ Diferencia no es estadísticamente significativa "
                f"(p-value: {statistical_tests['paired_t_test']['p_value']:.4f})"
            )
        else:
            reasons.append(
                f"✅ Diferencia es estadísticamente significativa "
                f"(p-value: {statistical_tests['paired_t_test']['p_value']:.4f})"
            )
        
        # Logging de decisión
        logger.info(f"\n{'🚀 DESPLEGAR MODELO B' if deploy else '⏸️  MANTENER MODELO A'}")
        logger.info("")
        for reason in reasons:
            logger.info(f"   {reason}")
        
        decision = {
            'deploy': deploy,
            'winner': 'MODEL_B' if deploy else 'MODEL_A',
            'reasons': reasons,
            'timestamp': datetime.now().isoformat()
        }
        
        return decision
    
    def should_deploy(self) -> bool:
        """
        ¿Se debe hacer deployment del modelo B?
        
        Returns:
            True si se debe desplegar modelo B
        """
        if not self.results:
            logger.warning("⚠️  No hay resultados de A/B test")
            return False
        
        return self.results['decision']['deploy']
    
    def get_winner(self) -> str:
        """
        Obtener modelo ganador
        
        Returns:
            'MODEL_A' o 'MODEL_B'
        """
        if not self.results:
            return 'MODEL_A'  # Default a producción
        
        return self.results['decision']['winner']
