"""
Feature Engineering - Cálculo de indicadores técnicos
"""
import pandas as pd
import numpy as np
from typing import Optional
from loguru import logger


class FeatureEngineer:
    """
    Calcula features técnicos y derivados para modelos de ML
    
    Features implementados:
    - Indicadores técnicos: RSI, MACD, Bollinger Bands, SMA, EMA
    - Features derivados: Returns, Volatilidad, Ratios
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Args:
            df: DataFrame con columnas OHLCV (debe tener índice datetime)
        """
        self.df = df.copy()
        
        if not isinstance(self.df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame debe tener índice DatetimeIndex")
    
    def add_all_features(self) -> pd.DataFrame:
        """
        Agregar todos los features disponibles
        
        Returns:
            DataFrame con features agregados
        """
        logger.info("🔧 Calculando features técnicos...")
        
        self.add_returns()
        self.add_volatility()
        self.add_rsi()
        self.add_macd()
        self.add_bollinger_bands()
        self.add_moving_averages()
        self.add_volume_features()
        
        logger.success(f"✅ Features calculados: {len(self.df.columns)} columnas")
        return self.df
    
    def add_returns(self, periods: list = [1, 5, 10, 21]) -> pd.DataFrame:
        """
        Calcular retornos para diferentes períodos
        
        Args:
            periods: Lista de períodos (días)
            
        Returns:
            DataFrame con columnas returns_Xd
        """
        for period in periods:
            col_name = f'returns_{period}d'
            self.df[col_name] = self.df['close'].pct_change(periods=period)
        
        return self.df
    
    def add_volatility(self, window: int = 21) -> pd.DataFrame:
        """
        Calcular volatilidad (desviación estándar de returns)
        
        Args:
            window: Ventana de cálculo (días)
            
        Returns:
            DataFrame con columna volatility_XXd
        """
        col_name = f'volatility_{window}d'
        
        # Calcular returns diarios si no existen
        if 'returns_1d' not in self.df.columns:
            self.df['returns_1d'] = self.df['close'].pct_change()
        
        self.df[col_name] = self.df['returns_1d'].rolling(window=window).std()
        
        return self.df
    
    def add_rsi(self, period: int = 14) -> pd.DataFrame:
        """
        Calcular RSI (Relative Strength Index)
        
        RSI = 100 - (100 / (1 + RS))
        donde RS = Average Gain / Average Loss
        
        Args:
            period: Período de cálculo (default: 14)
            
        Returns:
            DataFrame con columna rsi_XX
        """
        col_name = f'rsi_{period}'
        
        # Calcular cambios de precio
        delta = self.df['close'].diff()
        
        # Separar ganancias y pérdidas
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calcular promedios móviles
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Calcular RS y RSI
        rs = avg_gain / avg_loss
        self.df[col_name] = 100 - (100 / (1 + rs))
        
        return self.df
    
    def add_macd(
        self, 
        fast_period: int = 12, 
        slow_period: int = 26, 
        signal_period: int = 9
    ) -> pd.DataFrame:
        """
        Calcular MACD (Moving Average Convergence Divergence)
        
        MACD = EMA(fast) - EMA(slow)
        Signal = EMA(MACD, signal_period)
        Histogram = MACD - Signal
        
        Args:
            fast_period: Período EMA rápida (default: 12)
            slow_period: Período EMA lenta (default: 26)
            signal_period: Período señal (default: 9)
            
        Returns:
            DataFrame con columnas macd, macd_signal, macd_histogram
        """
        # Calcular EMAs
        ema_fast = self.df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = self.df['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD
        self.df['macd'] = ema_fast - ema_slow
        
        # Signal line
        self.df['macd_signal'] = self.df['macd'].ewm(span=signal_period, adjust=False).mean()
        
        # Histogram
        self.df['macd_histogram'] = self.df['macd'] - self.df['macd_signal']
        
        return self.df
    
    def add_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
        """
        Calcular Bollinger Bands
        
        Middle Band = SMA(period)
        Upper Band = Middle Band + (std_dev * std)
        Lower Band = Middle Band - (std_dev * std)
        
        Args:
            period: Período de cálculo (default: 20)
            std_dev: Desviaciones estándar (default: 2.0)
            
        Returns:
            DataFrame con columnas bb_upper, bb_middle, bb_lower
        """
        # Middle band (SMA)
        self.df['bb_middle'] = self.df['close'].rolling(window=period).mean()
        
        # Desviación estándar
        rolling_std = self.df['close'].rolling(window=period).std()
        
        # Upper y Lower bands
        self.df['bb_upper'] = self.df['bb_middle'] + (std_dev * rolling_std)
        self.df['bb_lower'] = self.df['bb_middle'] - (std_dev * rolling_std)
        
        # Bandwidth (útil para detectar squeeze)
        self.df['bb_bandwidth'] = (self.df['bb_upper'] - self.df['bb_lower']) / self.df['bb_middle']
        
        return self.df
    
    def add_moving_averages(
        self, 
        sma_periods: list = [20, 50, 200],
        ema_periods: list = [12, 26]
    ) -> pd.DataFrame:
        """
        Calcular SMA y EMA
        
        Args:
            sma_periods: Períodos para SMA
            ema_periods: Períodos para EMA
            
        Returns:
            DataFrame con columnas sma_XX y ema_XX
        """
        # Simple Moving Averages
        for period in sma_periods:
            col_name = f'sma_{period}'
            self.df[col_name] = self.df['close'].rolling(window=period).mean()
        
        # Exponential Moving Averages
        for period in ema_periods:
            col_name = f'ema_{period}'
            self.df[col_name] = self.df['close'].ewm(span=period, adjust=False).mean()
        
        return self.df
    
    def add_volume_features(self) -> pd.DataFrame:
        """
        Calcular features relacionados con volumen
        
        Returns:
            DataFrame con columnas de volumen
        """
        # Volumen moving average
        self.df['volume_ma_20'] = self.df['volume'].rolling(window=20).mean()
        
        # Volumen relativo (vs promedio 20 días)
        self.df['volume_relative'] = self.df['volume'] / self.df['volume_ma_20']
        
        # OBV (On-Balance Volume)
        self.df['obv'] = (np.sign(self.df['close'].diff()) * self.df['volume']).fillna(0).cumsum()
        
        return self.df
    
    def add_price_ratios(self) -> pd.DataFrame:
        """
        Calcular ratios de precios (High/Low, Close/Open, etc.)
        
        Returns:
            DataFrame con columnas de ratios
        """
        # High/Low ratio
        self.df['hl_ratio'] = self.df['high'] / self.df['low']
        
        # Close/Open ratio
        self.df['co_ratio'] = self.df['close'] / self.df['open']
        
        # (Close - Low) / (High - Low)
        self.df['position_in_range'] = (
            (self.df['close'] - self.df['low']) / 
            (self.df['high'] - self.df['low'])
        ).replace([np.inf, -np.inf], 0)
        
        return self.df
    
    def get_feature_columns(self, exclude_ohlcv: bool = False) -> list:
        """
        Obtener lista de columnas de features (excluye OHLCV si se indica)
        
        Args:
            exclude_ohlcv: Si True, excluye columnas OHLCV base
            
        Returns:
            Lista de nombres de columnas
        """
        if exclude_ohlcv:
            ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
            return [col for col in self.df.columns if col not in ohlcv_cols]
        else:
            return list(self.df.columns)
    
    def handle_nan_values(self, method: str = 'drop') -> pd.DataFrame:
        """
        Manejar valores NaN generados por indicadores
        
        Args:
            method: 'drop' o 'fill'
            
        Returns:
            DataFrame sin NaN
        """
        if method == 'drop':
            initial_len = len(self.df)
            self.df = self.df.dropna()
            dropped = initial_len - len(self.df)
            if dropped > 0:
                logger.warning(f"⚠️  Eliminados {dropped} registros con NaN")
        elif method == 'fill':
            self.df = self.df.fillna(method='ffill').fillna(method='bfill')
        
        return self.df


def calculate_sharpe_ratio(
    returns: pd.Series, 
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calcular Sharpe Ratio
    
    Sharpe = (Mean Return - Risk Free Rate) / Std Dev of Returns
    
    Args:
        returns: Serie de returns
        risk_free_rate: Tasa libre de riesgo anualizada
        periods_per_year: Períodos por año (252 para días de trading)
        
    Returns:
        Sharpe ratio anualizado
    """
    excess_returns = returns - (risk_free_rate / periods_per_year)
    return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()


def calculate_max_drawdown(prices: pd.Series) -> float:
    """
    Calcular Maximum Drawdown
    
    Args:
        prices: Serie de precios
        
    Returns:
        Maximum drawdown (valor negativo)
    """
    cumulative = (1 + prices.pct_change()).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()
