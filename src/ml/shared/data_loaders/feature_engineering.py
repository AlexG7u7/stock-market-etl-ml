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
        
        # Features básicos
        self.add_returns()
        self.add_volatility()
        self.add_rsi()
        self.add_macd()
        self.add_bollinger_bands()
        self.add_moving_averages()
        self.add_volume_features()
        self.add_price_ratios()
        
        # Features avanzados (nuevos)
        self.add_atr()
        self.add_adx()
        self.add_stochastic()
        self.add_momentum()
        self.add_price_position()
        self.add_candle_patterns()
        self.add_lag_features()
        
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
    
    def add_atr(self, period: int = 14) -> pd.DataFrame:
        """
        Calcular ATR (Average True Range) - mide volatilidad real
        
        True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        ATR = SMA(True Range, period)
        
        Args:
            period: Período de cálculo (default: 14)
            
        Returns:
            DataFrame con columna atr_XX
        """
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        prev_close = close.shift(1)
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR
        self.df[f'atr_{period}'] = true_range.rolling(window=period).mean()
        
        # ATR como % del precio (normalizado)
        self.df[f'atr_{period}_pct'] = self.df[f'atr_{period}'] / close * 100
        
        return self.df
    
    def add_adx(self, period: int = 14) -> pd.DataFrame:
        """
        Calcular ADX (Average Directional Index) - fuerza de tendencia
        
        ADX > 25 = tendencia fuerte
        ADX < 20 = mercado lateral
        
        Args:
            period: Período de cálculo (default: 14)
            
        Returns:
            DataFrame con columnas adx, plus_di, minus_di
        """
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        # +DM y -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        # ATR para normalización
        if f'atr_{period}' not in self.df.columns:
            self.add_atr(period)
        atr = self.df[f'atr_{period}']
        
        # +DI y -DI (smoothed)
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
        
        # DX y ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        self.df['plus_di'] = plus_di
        self.df['minus_di'] = minus_di
        self.df[f'adx_{period}'] = adx
        
        return self.df
    
    def add_stochastic(self, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
        """
        Calcular Stochastic Oscillator
        
        %K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
        %D = SMA(%K, d_period)
        
        Args:
            k_period: Período para %K (default: 14)
            d_period: Período para %D (default: 3)
            
        Returns:
            DataFrame con columnas stoch_k, stoch_d
        """
        low_min = self.df['low'].rolling(window=k_period).min()
        high_max = self.df['high'].rolling(window=k_period).max()
        
        # %K
        self.df['stoch_k'] = 100 * (self.df['close'] - low_min) / (high_max - low_min)
        
        # %D (señal)
        self.df['stoch_d'] = self.df['stoch_k'].rolling(window=d_period).mean()
        
        return self.df
    
    def add_momentum(self, periods: list = [10, 20]) -> pd.DataFrame:
        """
        Calcular Momentum y ROC (Rate of Change)
        
        Momentum = Close - Close(n periods ago)
        ROC = (Close - Close(n)) / Close(n) * 100
        
        Args:
            periods: Lista de períodos
            
        Returns:
            DataFrame con columnas momentum_X, roc_X
        """
        for period in periods:
            # Momentum absoluto
            self.df[f'momentum_{period}'] = self.df['close'] - self.df['close'].shift(period)
            
            # ROC (porcentual)
            self.df[f'roc_{period}'] = (
                (self.df['close'] - self.df['close'].shift(period)) / 
                self.df['close'].shift(period) * 100
            )
        
        return self.df
    
    def add_price_position(self) -> pd.DataFrame:
        """
        Calcular posición del precio relativa a promedios móviles
        
        Útil para detectar tendencia y puntos de reversión
        
        Returns:
            DataFrame con columnas de posición relativa
        """
        close = self.df['close']
        
        # Asegurar que existan las SMAs
        if 'sma_20' not in self.df.columns:
            self.df['sma_20'] = close.rolling(window=20).mean()
        if 'sma_50' not in self.df.columns:
            self.df['sma_50'] = close.rolling(window=50).mean()
        if 'sma_200' not in self.df.columns:
            self.df['sma_200'] = close.rolling(window=200).mean()
        
        # Distancia porcentual a SMAs
        self.df['dist_sma_20'] = (close - self.df['sma_20']) / self.df['sma_20'] * 100
        self.df['dist_sma_50'] = (close - self.df['sma_50']) / self.df['sma_50'] * 100
        self.df['dist_sma_200'] = (close - self.df['sma_200']) / self.df['sma_200'] * 100
        
        # Posición en rango de 52 semanas (252 días)
        high_52w = close.rolling(window=252).max()
        low_52w = close.rolling(window=252).min()
        self.df['position_52w'] = (close - low_52w) / (high_52w - low_52w) * 100
        
        # Distancia a máximo/mínimo de 52 semanas
        self.df['dist_high_52w'] = (close - high_52w) / high_52w * 100
        self.df['dist_low_52w'] = (close - low_52w) / low_52w * 100
        
        return self.df
    
    def add_candle_patterns(self) -> pd.DataFrame:
        """
        Calcular patrones de velas simplificados
        
        Returns:
            DataFrame con features de velas
        """
        open_p = self.df['open']
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        # Tamaño del cuerpo (absoluto y relativo)
        body = abs(close - open_p)
        candle_range = high - low
        
        self.df['body_size'] = body
        self.df['body_pct'] = body / candle_range  # Qué % del rango es cuerpo
        
        # Sombras
        upper_shadow = high - pd.concat([open_p, close], axis=1).max(axis=1)
        lower_shadow = pd.concat([open_p, close], axis=1).min(axis=1) - low
        
        self.df['upper_shadow_pct'] = upper_shadow / candle_range
        self.df['lower_shadow_pct'] = lower_shadow / candle_range
        
        # Vela alcista/bajista (1 = alcista, 0 = bajista)
        self.df['bullish'] = (close > open_p).astype(int)
        
        # Secuencia de velas alcistas/bajistas
        self.df['bullish_streak'] = self.df['bullish'].groupby(
            (self.df['bullish'] != self.df['bullish'].shift()).cumsum()
        ).cumcount() + 1
        self.df['bullish_streak'] = self.df['bullish_streak'] * (2 * self.df['bullish'] - 1)
        
        # Doji (cuerpo muy pequeño)
        self.df['is_doji'] = (self.df['body_pct'] < 0.1).astype(int)
        
        return self.df
    
    def add_lag_features(self, lags: list = [1, 2, 3, 5]) -> pd.DataFrame:
        """
        Agregar features con lag (valores de días anteriores)
        
        Útil para que el modelo capture patrones temporales
        
        Args:
            lags: Lista de días de lag
            
        Returns:
            DataFrame con features lagged
        """
        # Lag de returns
        if 'returns_1d' not in self.df.columns:
            self.df['returns_1d'] = self.df['close'].pct_change()
        
        for lag in lags:
            self.df[f'returns_lag_{lag}'] = self.df['returns_1d'].shift(lag)
        
        # Lag de volumen relativo
        if 'volume_relative' not in self.df.columns:
            self.df['volume_ma_20'] = self.df['volume'].rolling(window=20).mean()
            self.df['volume_relative'] = self.df['volume'] / self.df['volume_ma_20']
        
        for lag in lags:
            self.df[f'volume_rel_lag_{lag}'] = self.df['volume_relative'].shift(lag)
        
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
