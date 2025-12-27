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
            
        La API devuelve estructura anidada:
        {
            "EMISORA": {
                "SERIE": {
                    "razon_social": "...",
                    "isin": "...",
                    ...
                }
            }
        }
        """
        logger.info("📊 Obteniendo catálogo de emisoras...")
        data = self._make_request("/v2/emisoras")
        
        logger.info(f"Respuesta de API: {type(data)}")
        
        # Parsear estructura anidada: EMISORA -> SERIE -> datos
        emisoras = []
        
        if isinstance(data, dict):
            for emisora_code, series_dict in data.items():
                if emisora_code == 'null' or not series_dict:
                    continue
                
                # series_dict es un dict con las series como keys (ej: {"*": {...}, "A": {...}})
                if isinstance(series_dict, dict):
                    for serie_code, info in series_dict.items():
                        if isinstance(info, dict):
                            # Crear registro con emisora, serie y datos
                            registro = {
                                'emisora': emisora_code,
                                'serie': serie_code,
                                'emisora_serie': f"{emisora_code}{serie_code}" if serie_code != '*' else emisora_code,
                                **info  # Desempaquetar el resto de los campos
                            }
                            emisoras.append(registro)
        
        logger.info(f"✅ Obtenidas {len(emisoras)} emisoras/series")
        
        if len(emisoras) > 0:
            logger.info(f"Ejemplo de emisora: {emisoras[0]}")
        
        return emisoras
    
    def get_historicos(
        self, 
        emisora_serie: str, 
        fecha_inicio: str, 
        fecha_fin: str
    ) -> List[Dict]:
        """
        Obtener precios históricos de un ticker
        
        Args:
            emisora_serie: Símbolo del ticker con serie (ej: 'ALFAA', 'ALSEA*')
            fecha_inicio: Fecha inicial en formato 'YYYY-MM-DD'
            fecha_fin: Fecha final en formato 'YYYY-MM-DD'
            
        Returns:
            Lista de diccionarios con precios históricos
            Ejemplo: [
                {
                    "fecha": "2024-12-01",
                    "precio": 15.50,
                    "importe": 1234567.89
                },
                ...
            ]
            
        Nota: La API solo devuelve precio de cierre e importe, no OHLCV completo
        """
        logger.info(f"📈 Obteniendo históricos de {emisora_serie} ({fecha_inicio} a {fecha_fin})")
        
        # Parámetros correctos según documentación
        params = {
            "emisora_serie": emisora_serie,
            "inicio": fecha_inicio,
            "final": fecha_fin
        }
        
        data = self._make_request("/v2/historicos", params=params)
        
        # Verificar si hay error
        if 'Error' in data:
            logger.error(f"❌ Error en API: {data.get('Error')}")
            return []
        
        # La respuesta es un dict donde las keys son las fechas
        # Necesitamos convertirlo a lista
        historicos = []
        
        if isinstance(data, dict):
            for fecha, info in data.items():
                if isinstance(info, dict):
                    registro = {
                        'fecha': fecha,
                        **info
                    }
                    historicos.append(registro)
        
        logger.info(f"✅ Obtenidos {len(historicos)} registros históricos para {emisora_serie}")
        
        return historicos
    
    def get_cotizaciones(self, emisora_serie: str, bolsa: str = "BMV") -> Dict:
        """
        Obtener cotización más reciente de un ticker (intradía)
        
        Args:
            emisora_serie: Símbolo del ticker con serie (ej: 'ALFAA')
            bolsa: Bolsa de valores ('BMV' o 'BIVA'). Default: 'BMV'
            
        Returns:
            Diccionario con cotización actual
            Ejemplo: {
                "ALFAA": {
                    "bolsa": "BMV",
                    "u": 15.50,      # último
                    "p": 15.45,      # ppp
                    "a": 15.40,      # anterior
                    "x": 15.60,      # máximo
                    "n": 15.30,      # mínimo
                    "c": 0.65,       # cambio %
                    "m": 0.10,       # cambio $
                    "v": 1234567,    # volumen
                    "o": 500,        # operaciones
                    "i": 19123456.78,# importe
                    "f": "2025-12-26"# fecha
                }
            }
        """
        logger.info(f"💹 Obteniendo cotización intradía de {emisora_serie} en {bolsa}")
        
        params = {
            "emisora_serie": emisora_serie,
            "concepto": "u,p,a,x,n,c,m,v,o,i",  # todos los conceptos
            "bolsa": bolsa.lower()
        }
        
        data = self._make_request("/v2/intradia", params=params)
        
        return data
