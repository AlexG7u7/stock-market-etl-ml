"""
Wrapper para la API de DataBursátil México
https://databursatilmexico.com/api/docs
"""

import requests
import time
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataBursatilAPI:
    """Cliente para la API de DataBursátil México"""
    
    BASE_URL = "https://api.databursatil.com"
    
    def __init__(self, api_token: str):
        """
        Inicializar cliente de API
        
        Args:
            api_token: Token de acceso a la API
        """
        self.api_token = api_token
        self.session = requests.Session()
        # No usar headers de autorización, el token va en query params
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Medio segundo entre requests
        
    def _wait_rate_limit(self):
        """Esperar el tiempo necesario para respetar rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None, max_retries: int = 3) -> Dict:
        """
        Hacer request a la API con retry logic
        
        Args:
            endpoint: Endpoint de la API (ej: '/v2/emisoras')
            params: Parámetros query string
            max_retries: Número máximo de reintentos
            
        Returns:
            Respuesta JSON de la API
            
        Raises:
            requests.exceptions.RequestException: Si falla después de reintentos
        """
        self._wait_rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        # Agregar token a los parámetros
        if params is None:
            params = {}
        params['token'] = self.api_token
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Request a {endpoint} (intento {attempt + 1}/{max_retries})")
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                logger.info(f"✅ Request exitoso: {endpoint}")
                return data
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error en request (intento {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Backoff exponencial: 1s, 2s, 4s
                    logger.info(f"Reintentando en {wait_time} segundos...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Request falló después de {max_retries} intentos")
                    raise
    
    def get_emisoras(self) -> List[Dict]:
        """
        Obtener catálogo completo de emisoras/tickers
        
        Returns:
            Lista de diccionarios con información de emisoras
        """
        logger.info("📊 Obteniendo catálogo de emisoras...")
        data = self._make_request("/v2/emisoras")
        
        # Debug: mostrar estructura de respuesta
        logger.info(f"Respuesta de API: {type(data)}")
        
        # La API devuelve un dict donde las keys son los símbolos
        # Necesitamos convertirlo a lista
        emisoras = []
        
        if isinstance(data, dict):
            for symbol, info in data.items():
                if symbol != 'null' and info:  # Filtrar null y valores vacíos
                    # Agregar el símbolo al diccionario de información
                    if isinstance(info, dict):
                        info['ticker'] = symbol  # Ticker completo (emisora + serie)
                        emisoras.append(info)
                    else:
                        # Si solo es el símbolo, crear dict básico
                        emisoras.append({'ticker': symbol})
        elif isinstance(data, list):
            emisoras = data
        
        logger.info(f"✅ Obtenidas {len(emisoras)} emisoras")
        
        if len(emisoras) > 0:
            logger.info(f"Ejemplo de emisora (primeros 3 campos): {dict(list(emisoras[0].items())[:3])}")
            logger.info(f"Campos disponibles: {list(emisoras[0].keys())}")
        
        return emisoras
    
    def get_historicos(
        self, 
        ticker: str, 
        fecha_inicio: str, 
        fecha_fin: str
    ) -> List[Dict]:
        """
        Obtener precios históricos de un ticker
        
        Args:
            ticker: Símbolo del ticker (ej: 'ALFAA')
            fecha_inicio: Fecha inicial en formato 'YYYY-MM-DD'
            fecha_fin: Fecha final en formato 'YYYY-MM-DD'
            
        Returns:
            Lista de diccionarios con precios históricos
            Ejemplo: [
                {
                    "fecha": "2024-01-15",
                    "open": 15.50,
                    "high": 15.80,
                    "low": 15.40,
                    "close": 15.75,
                    "volume": 1000000
                },
                ...
            ]
        """
        logger.info(f"📈 Obteniendo históricos de {ticker} ({fecha_inicio} a {fecha_fin})")
        
        params = {
            "ticker": ticker,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin
        }
        
        data = self._make_request("/v2/historicos", params=params)
        historicos = data.get("results", [])
        
        logger.info(f"✅ Obtenidos {len(historicos)} registros históricos para {ticker}")
        
        return historicos
    
    def get_cotizaciones(self, ticker: str) -> Dict:
        """
        Obtener cotización más reciente de un ticker
        
        Args:
            ticker: Símbolo del ticker (ej: 'ALFAA')
            
        Returns:
            Diccionario con cotización actual
        """
        logger.info(f"💹 Obteniendo cotización actual de {ticker}")
        
        params = {"ticker": ticker}
        data = self._make_request("/v2/cotizaciones", params=params)
        
        return data.get("result", {})
