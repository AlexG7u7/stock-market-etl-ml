#!/usr/bin/env python3
"""
ETL Incremental para WALMEX
Ejecuta carga diaria (último día disponible)
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.etl.shared.extractors import YahooFinanceExtractor
from src.etl.shared.loaders import SQLServerLoader


# Configuración de WALMEX
TICKER_SYMBOL = "WALMEX*"
EMISORA = "WALMEX"
SERIE = "*"
TICKER_ID = None  # Se obtendrá de la BD


def get_ticker_id(loader: SQLServerLoader) -> int:
    """Obtiene el ticker_id de WALMEX desde la BD"""
    loader.connect()
    cursor = loader._connection.cursor()
    
    try:
        cursor.execute(
            "SELECT ticker_id FROM stage.cat_tickers WHERE emisora = ? AND serie = ?",
            (EMISORA, SERIE)
        )
        result = cursor.fetchone()
        
        if result:
            return result[0]
        else:
            raise ValueError(f"Ticker {EMISORA}{SERIE} no encontrado en stage.cat_tickers. Ejecuta: python scripts\\setup_tickers.py")
    
    finally:
        cursor.close()


def run(lookback_days: int = 1):
    """
    Ejecuta el ETL incremental de WALMEX
    
    Args:
        lookback_days: Días hacia atrás a cargar (default: 1 = ayer)
    """
    logger.info("=" * 80)
    logger.info(f"ETL INCREMENTAL - WALMEX - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Configurar loader
    loader = SQLServerLoader(
        server=os.getenv('SQL_SERVER'),
        database=os.getenv('SQL_DATABASE'),
        username=os.getenv('SQL_USER'),
        password=os.getenv('SQL_PASSWORD')
    )
    
    try:
        # Obtener ticker_id
        ticker_id = get_ticker_id(loader)
        logger.info(f"Ticker ID de {TICKER_SYMBOL}: {ticker_id}")
        
        # Configurar extractor
        extractor = YahooFinanceExtractor(
            ticker_symbol=TICKER_SYMBOL,
            ticker_id=ticker_id
        )
        
        # EXTRACT
        logger.info(f"Extrayendo últimos {lookback_days} días de {TICKER_SYMBOL}...")
        precios = extractor.extract_incremental(lookback_days=lookback_days)
        
        if not precios:
            logger.warning("No se obtuvieron datos. Finalizando.")
            return
        
        # LOAD
        logger.info(f"Cargando {len(precios)} registros a la base de datos...")
        stats = loader.load(precios)
        
        # Resumen
        logger.success("=" * 80)
        logger.success("ETL COMPLETADO EXITOSAMENTE")
        logger.success(f"Insertados: {stats['inserted']}")
        logger.success(f"Actualizados: {stats['updated']}")
        logger.success(f"Errores: {stats['errors']}")
        logger.success("=" * 80)
        
    except Exception as e:
        logger.error(f"Error en ETL incremental: {str(e)}")
        raise
    
    finally:
        loader.disconnect()


if __name__ == "__main__":
    # Configurar logging
    logger.remove()  # Remover handler por defecto
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    run()
