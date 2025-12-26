"""
Wrapper para Yahoo Finance API
Obtener datos históricos OHLCV de tickers mexicanos
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class YahooFinanceAPI:
    """Cliente para Yahoo Finance"""
    
    # Sufijos de mercado para tickers mexicanos
    SUFIJOS_MEXICO = {
        'BMV': '.MX',      # Bolsa Mexicana de Valores
        'BIVA': '.MX'      # También usan .MX en Yahoo
    }
    
    def __init__(self):
        """Inicializar cliente de Yahoo Finance"""
        logger.info("📊 Cliente Yahoo Finance inicializado")
    
    def _convertir_ticker(self, emisora_serie: str, bolsa: str = 'BMV') -> str:
        """
        Convertir ticker mexicano a formato Yahoo Finance
        
        Args:
            emisora_serie: Ticker mexicano (ej: 'ALFAA', 'WALMEX*')
            bolsa: Bolsa (BMV o BIVA)
            
        Returns:
            Ticker en formato Yahoo (ej: 'ALFAA.MX')
        """
        # Remover el asterisco si existe
        ticker_limpio = emisora_serie.replace('*', '')
        
        # Agregar sufijo de mercado
        sufijo = self.SUFIJOS_MEXICO.get(bolsa, '.MX')
        ticker_yahoo = f"{ticker_limpio}{sufijo}"
        
        return ticker_yahoo
    
    def get_historicos(
        self,
        emisora_serie: str,
        fecha_inicio: str,
        fecha_fin: str,
        bolsa: str = 'BMV'
    ) -> List[Dict]:
        """
        Obtener precios históricos OHLCV de Yahoo Finance
        
        Args:
            emisora_serie: Ticker mexicano (ej: 'ALFAA', 'WALMEX*')
            fecha_inicio: Fecha inicio en formato 'YYYY-MM-DD'
            fecha_fin: Fecha fin en formato 'YYYY-MM-DD'
            bolsa: Bolsa (BMV o BIVA)
            
        Returns:
            Lista de diccionarios con datos OHLCV
            Ejemplo: [
                {
                    "fecha": "2024-12-01",
                    "open": 15.50,
                    "high": 15.80,
                    "low": 15.40,
                    "close": 15.75,
                    "volume": 1000000,
                    "adj_close": 15.75
                },
                ...
            ]
        """
        ticker_yahoo = self._convertir_ticker(emisora_serie, bolsa)
        
        logger.info(f"📈 Obteniendo históricos de {emisora_serie} ({ticker_yahoo}) desde Yahoo Finance")
        logger.info(f"   Rango: {fecha_inicio} a {fecha_fin}")
        
        try:
            # Crear objeto Ticker
            ticker = yf.Ticker(ticker_yahoo)
            
            # Descargar datos históricos
            df = ticker.history(
                start=fecha_inicio,
                end=fecha_fin,
                auto_adjust=False,  # No ajustar precios automáticamente
                actions=False       # No incluir dividendos/splits
            )
            
            if df.empty:
                logger.warning(f"⚠️  No se obtuvieron datos para {ticker_yahoo}")
                return []
            
            # Convertir DataFrame a lista de diccionarios
            historicos = []
            for fecha, row in df.iterrows():
                registro = {
                    'fecha': fecha.strftime('%Y-%m-%d'),
                    'open': round(float(row['Open']), 4) if pd.notna(row['Open']) else None,
                    'high': round(float(row['High']), 4) if pd.notna(row['High']) else None,
                    'low': round(float(row['Low']), 4) if pd.notna(row['Low']) else None,
                    'close': round(float(row['Close']), 4) if pd.notna(row['Close']) else None,
                    'volume': int(row['Volume']) if pd.notna(row['Volume']) else None,
                }
                historicos.append(registro)
            
            logger.info(f"✅ Obtenidos {len(historicos)} registros históricos para {emisora_serie}")
            
            return historicos
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Yahoo Finance para {ticker_yahoo}: {e}")
            return []
    
    def get_info(self, emisora_serie: str, bolsa: str = 'BMV') -> Dict:
        """
        Obtener información general de un ticker
        
        Args:
            emisora_serie: Ticker mexicano
            bolsa: Bolsa (BMV o BIVA)
            
        Returns:
            Diccionario con información del ticker
        """
        ticker_yahoo = self._convertir_ticker(emisora_serie, bolsa)
        
        try:
            ticker = yf.Ticker(ticker_yahoo)
            info = ticker.info
            
            return {
                'ticker': emisora_serie,
                'ticker_yahoo': ticker_yahoo,
                'nombre': info.get('longName') or info.get('shortName'),
                'sector': info.get('sector'),
                'industria': info.get('industry'),
                'moneda': info.get('currency'),
                'mercado': info.get('exchange'),
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo info de {ticker_yahoo}: {e}")
            return {}
    
    def validar_ticker(self, emisora_serie: str, bolsa: str = 'BMV') -> bool:
        """
        Verificar si un ticker existe en Yahoo Finance
        
        Args:
            emisora_serie: Ticker mexicano
            bolsa: Bolsa (BMV o BIVA)
            
        Returns:
            True si el ticker existe, False en caso contrario
        """
        ticker_yahoo = self._convertir_ticker(emisora_serie, bolsa)
        
        try:
            ticker = yf.Ticker(ticker_yahoo)
            # Intentar obtener un dato histórico reciente
            df = ticker.history(period='5d')
            return not df.empty
            
        except:
            return False
