"""
Extractor de datos de Yahoo Finance
Fuente principal y confiable para datos OHLCV de la BMV
"""
import yfinance as yf
from datetime import datetime, timedelta, date
from typing import List, Optional
from loguru import logger

from ..models.precio import PrecioHistorico


class YahooFinanceExtractor:
    """
    Extractor genérico para obtener datos de Yahoo Finance
    Maneja cualquier ticker de la BMV
    """
    
    def __init__(self, ticker_symbol: str, ticker_id: int):
        """
        Inicializa el extractor
        
        Args:
            ticker_symbol: Símbolo del ticker (ej: WALMEX*, ALSEA*, ALFAA)
            ticker_id: ID del ticker en la base de datos
        """
        self.ticker_symbol = ticker_symbol
        self.ticker_id = ticker_id
        # Formato para Yahoo Finance: TICKER.MX (sin asterisco)
        self.yahoo_symbol = f"{ticker_symbol.replace('*', '')}.MX"
        logger.info(f"Extractor inicializado para {ticker_symbol} → {self.yahoo_symbol}")
    
    def extract_incremental(self, lookback_days: int = 1) -> List[PrecioHistorico]:
        """
        Extrae datos incrementales (últimos N días hábiles)
        
        Args:
            lookback_days: Días hacia atrás a consultar (default: 1 = último día hábil)
            
        Returns:
            Lista de PrecioHistorico
        """
        # Calcular fecha de inicio considerando fines de semana
        hoy = datetime.now()
        dia_semana = hoy.weekday()  # 0=Lunes, 6=Domingo
        
        if dia_semana == 0:  # Lunes
            # Saltar sábado y domingo: traer viernes (3 días atrás)
            fecha_inicio = (hoy - timedelta(days=3)).date()
        elif dia_semana == 6:  # Domingo
            # Traer viernes (2 días atrás)
            fecha_inicio = (hoy - timedelta(days=2)).date()
        else:  # Martes a Sábado
            # Traer día anterior
            fecha_inicio = (hoy - timedelta(days=lookback_days)).date()
        
        fecha_fin = hoy.date()
        
        logger.info(f"Extrayendo datos incrementales de {self.ticker_symbol}: {fecha_inicio} a {fecha_fin}")
        
        return self._extract_range(fecha_inicio, fecha_fin)
    
    def extract_historical(
        self, 
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None
    ) -> List[PrecioHistorico]:
        """
        Extrae datos históricos en un rango de fechas
        
        Args:
            fecha_inicio: Fecha de inicio (default: hace 1 año)
            fecha_fin: Fecha de fin (default: hoy)
            
        Returns:
            Lista de PrecioHistorico
        """
        if fecha_inicio is None:
            fecha_inicio = (datetime.now() - timedelta(days=365)).date()
        
        if fecha_fin is None:
            fecha_fin = datetime.now().date()
        
        logger.info(f"Extrayendo datos históricos de {self.ticker_symbol}: {fecha_inicio} a {fecha_fin}")
        
        return self._extract_range(fecha_inicio, fecha_fin)
    
    def _extract_range(self, fecha_inicio: date, fecha_fin: date) -> List[PrecioHistorico]:
        """
        Extrae datos en un rango de fechas específico
        
        Args:
            fecha_inicio: Fecha de inicio
            fecha_fin: Fecha de fin
            
        Returns:
            Lista de PrecioHistorico
        """
        try:
            # Obtener datos de Yahoo Finance
            ticker = yf.Ticker(self.yahoo_symbol)
            hist = ticker.history(
                start=fecha_inicio.strftime('%Y-%m-%d'),
                end=(fecha_fin + timedelta(days=1)).strftime('%Y-%m-%d')  # Yahoo usa end exclusive
            )
            
            if hist.empty:
                logger.warning(f"No se obtuvieron datos de Yahoo Finance para {self.ticker_symbol}")
                return []
            
            # Convertir a lista de PrecioHistorico
            precios = []
            for idx, row in hist.iterrows():
                precio = PrecioHistorico(
                    ticker_id=self.ticker_id,
                    fecha=idx.date(),
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=int(row['Volume']) if row['Volume'] > 0 else 0
                )
                precios.append(precio)
            
            logger.success(f"Extraídos {len(precios)} registros de {self.ticker_symbol}")
            
            # Log de resumen
            if precios:
                logger.info(f"Primera fecha: {precios[0].fecha}, Última fecha: {precios[-1].fecha}")
                con_volumen = sum(1 for p in precios if p.volume and p.volume > 0)
                sin_volumen = len(precios) - con_volumen
                logger.info(f"Con volumen: {con_volumen}, Sin volumen: {sin_volumen}")
            
            return precios
            
        except Exception as e:
            logger.error(f"Error extrayendo datos de {self.ticker_symbol}: {str(e)}")
            raise
    
    def extract_latest(self) -> Optional[PrecioHistorico]:
        """
        Extrae solo el último dato disponible
        
        Returns:
            PrecioHistorico del último día, o None si no hay datos
        """
        precios = self.extract_incremental(lookback_days=5)  # Busca en últimos 5 días
        
        if not precios:
            return None
        
        # Retornar el más reciente
        return max(precios, key=lambda p: p.fecha)
