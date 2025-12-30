"""
Metrics - Suite completa de métricas para evaluación de modelos
"""
import numpy as np
from typing import Dict, Tuple
from loguru import logger


class Metrics:
    """
    Suite completa de métricas para modelos de predicción
    
    Métricas implementadas:
    - RMSE: Root Mean Squared Error
    - MAE: Mean Absolute Error
    - MAPE: Mean Absolute Percentage Error
    - R²: Coeficiente de determinación
    - Win Rate: Proporción de direcciones correctas
    - Sharpe Ratio: Retorno ajustado por riesgo
    - Max Drawdown: Máxima caída desde pico
    - Calmar Ratio: Retorno anualizado / Max Drawdown
    - Sortino Ratio: Sharpe pero solo con downside volatility
    """
    
    @staticmethod
    def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Root Mean Squared Error
        
        RMSE penaliza más los errores grandes
        """
        return np.sqrt(np.mean((y_true - y_pred) ** 2))
    
    @staticmethod
    def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Mean Absolute Error
        
        MAE trata todos los errores por igual
        """
        return np.mean(np.abs(y_true - y_pred))
    
    @staticmethod
    def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Mean Absolute Percentage Error
        
        MAPE expresa error como porcentaje
        """
        # Evitar división por cero
        mask = y_true != 0
        return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    
    @staticmethod
    def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        R² - Coeficiente de determinación
        
        R² = 1 indica predicción perfecta
        R² = 0 indica predicción igual a la media
        R² < 0 indica predicción peor que la media
        """
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        
        if ss_tot == 0:
            return 0.0
        
        return 1 - (ss_res / ss_tot)
    
    @staticmethod
    def direction_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Accuracy de la dirección del cambio
        
        ¿Predijimos correctamente si sube o baja?
        """
        if len(y_true) < 2:
            return 0.0
        
        # Calcular cambios
        true_changes = np.diff(y_true)
        pred_changes = np.diff(y_pred)
        
        # Comparar direcciones (mismo signo = correcto)
        correct = np.sum(np.sign(true_changes) == np.sign(pred_changes))
        
        return correct / len(true_changes)
    
    @staticmethod
    def sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
        """
        Sharpe Ratio - Retorno ajustado por riesgo
        
        Sharpe = (Retorno promedio - Risk free rate) / Volatilidad
        
        Args:
            returns: Serie de retornos
            risk_free_rate: Tasa libre de riesgo anualizada (default 0%)
        """
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        
        # Convertir risk_free_rate anual a diario
        daily_rf = (1 + risk_free_rate) ** (1/252) - 1
        
        excess_returns = returns - daily_rf
        
        return np.mean(excess_returns) / np.std(returns) * np.sqrt(252)
    
    @staticmethod
    def sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
        """
        Sortino Ratio - Similar a Sharpe pero solo penaliza downside
        
        Sortino = (Retorno promedio - Risk free rate) / Downside Deviation
        """
        if len(returns) == 0:
            return 0.0
        
        # Convertir risk_free_rate anual a diario
        daily_rf = (1 + risk_free_rate) ** (1/252) - 1
        
        excess_returns = returns - daily_rf
        
        # Solo retornos negativos para downside deviation
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0.0
        
        downside_std = np.std(downside_returns)
        
        return np.mean(excess_returns) / downside_std * np.sqrt(252)
    
    @staticmethod
    def max_drawdown(cumulative_returns: np.ndarray) -> float:
        """
        Maximum Drawdown - Máxima caída desde pico
        
        Args:
            cumulative_returns: Retornos acumulados (curva de capital)
        """
        if len(cumulative_returns) == 0:
            return 0.0
        
        # Calcular picos acumulados
        running_max = np.maximum.accumulate(cumulative_returns)
        
        # Calcular drawdown en cada punto
        drawdown = (cumulative_returns - running_max) / running_max
        
        return np.min(drawdown)
    
    @staticmethod
    def calmar_ratio(returns: np.ndarray, cumulative_returns: np.ndarray) -> float:
        """
        Calmar Ratio - Retorno anualizado / Max Drawdown
        
        Mide retorno ajustado por máxima caída
        """
        annual_return = np.mean(returns) * 252
        mdd = abs(Metrics.max_drawdown(cumulative_returns))
        
        if mdd == 0:
            return 0.0
        
        return annual_return / mdd
    
    @staticmethod
    def win_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Win Rate - Proporción de predicciones direccionales correctas
        
        Similar a direction_accuracy pero más simple
        """
        if len(y_true) < 2:
            return 0.0
        
        # Calcular retornos
        true_returns = np.diff(y_true) / y_true[:-1]
        pred_returns = np.diff(y_pred) / y_pred[:-1]
        
        # Comparar signos
        correct = np.sum(np.sign(true_returns) == np.sign(pred_returns))
        
        return correct / len(true_returns)
    
    @staticmethod
    def calculate_all_metrics(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        risk_free_rate: float = 0.0
    ) -> Dict[str, float]:
        """
        Calcular todas las métricas de una vez
        
        Args:
            y_true: Valores reales
            y_pred: Valores predichos
            risk_free_rate: Tasa libre de riesgo anualizada
            
        Returns:
            Dict con todas las métricas
        """
        # Convertir a numpy
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        
        # Métricas básicas
        metrics = {
            'rmse': Metrics.rmse(y_true, y_pred),
            'mae': Metrics.mae(y_true, y_pred),
            'mape': Metrics.mape(y_true, y_pred),
            'r2': Metrics.r2_score(y_true, y_pred),
            'direction_accuracy': Metrics.direction_accuracy(y_true, y_pred),
            'win_rate': Metrics.win_rate(y_true, y_pred)
        }
        
        # Métricas basadas en retornos
        if len(y_true) >= 2:
            returns = np.diff(y_true) / y_true[:-1]
            cumulative_returns = np.cumprod(1 + returns) - 1
            
            metrics.update({
                'sharpe_ratio': Metrics.sharpe_ratio(returns, risk_free_rate),
                'sortino_ratio': Metrics.sortino_ratio(returns, risk_free_rate),
                'max_drawdown': Metrics.max_drawdown(cumulative_returns),
                'calmar_ratio': Metrics.calmar_ratio(returns, cumulative_returns)
            })
        
        return metrics
    
    @staticmethod
    def print_metrics(metrics: Dict[str, float]):
        """
        Imprimir métricas en formato legible
        
        Args:
            metrics: Dict con métricas
        """
        logger.info("📊 MÉTRICAS DE EVALUACIÓN")
        logger.info("=" * 50)
        
        # Agrupar métricas
        error_metrics = ['rmse', 'mae', 'mape']
        quality_metrics = ['r2', 'direction_accuracy', 'win_rate']
        risk_metrics = ['sharpe_ratio', 'sortino_ratio', 'max_drawdown', 'calmar_ratio']
        
        logger.info("📉 Métricas de Error:")
        for metric in error_metrics:
            if metric in metrics:
                logger.info(f"   {metric.upper()}: {metrics[metric]:.6f}")
        
        logger.info("\n📈 Métricas de Calidad:")
        for metric in quality_metrics:
            if metric in metrics:
                if metric in ['direction_accuracy', 'win_rate']:
                    logger.info(f"   {metric.replace('_', ' ').title()}: {metrics[metric]*100:.2f}%")
                else:
                    logger.info(f"   {metric.upper()}: {metrics[metric]:.6f}")
        
        logger.info("\n⚖️  Métricas de Riesgo:")
        for metric in risk_metrics:
            if metric in metrics:
                logger.info(f"   {metric.replace('_', ' ').title()}: {metrics[metric]:.6f}")
        
        logger.info("=" * 50)
