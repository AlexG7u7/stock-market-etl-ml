#!/usr/bin/env python3
"""
ETL Histórico para ALSEA
Ejecuta carga de múltiples años (backfill)
"""
import os
import sys
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.etl.shared.extractors import YahooFinanceExtractor
from src.etl.shared.loaders import SQLServerLoader


# Configuración de ALSEA
TICKER_SYMBOL = "ALSEA*"
TICKER_ID = None  # Se obtendrá de la BD


def get_ticker_id(loader: SQLServerLoader) -> int:
    """Obtiene el ticker_id de ALSEA desde la BD"""
    loader.connect()
    cursor = loader._connection.cursor()
    
    try:
        cursor.execute(
            "SELECT ticker_id FROM stage.cat_tickers WHERE emisora_serie = ?",
            (TICKER_SYMBOL,)
        )
        result = cursor.fetchone()
        
        if result:
            return result[0]
        else:
            raise ValueError(f"Ticker {TICKER_SYMBOL} no encontrado en stage.cat_tickers")
    
    finally:
        cursor.close()


def run(fecha_inicio: str = "2024-12-27", fecha_fin: str = None):
    """
    Ejecuta el ETL histórico de ALSEA
    
    Args:
        fecha_inicio: Fecha de inicio en formato YYYY-MM-DD (default: 2024-12-27)
        fecha_fin: Fecha de fin en formato YYYY-MM-DD (default: hoy)
    """
    logger.info("=" * 80)
    logger.info(f"ETL HISTÓRICO - ALSEA - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Parsear fechas
    fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date() if fecha_fin else date.today()
    
    logger.info(f"Rango de carga: {fecha_inicio_dt} hasta {fecha_fin_dt}")
    
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
        logger.info(f"Extrayendo datos históricos de {TICKER_SYMBOL}...")
        precios = extractor.extract_historical(
            fecha_inicio=fecha_inicio_dt,
            fecha_fin=fecha_fin_dt
        )
        
        if not precios:
            logger.warning("No se obtuvieron datos. Finalizando.")
            return
        
        # LOAD
        logger.info(f"Cargando {len(precios)} registros a la base de datos...")
        stats = loader.load(precios, batch_size=100)
        
        # Resumen
        logger.success("=" * 80)
        logger.success("ETL COMPLETADO EXITOSAMENTE")
        logger.success(f"Periodo: {fecha_inicio_dt} a {fecha_fin_dt}")
        logger.success(f"Insertados: {stats['inserted']}")
        logger.success(f"Actualizados: {stats['updated']}")
        logger.success(f"Errores: {stats['errors']}")
        logger.success("=" * 80)
        
    except Exception as e:
        logger.error(f"Error en ETL histórico: {str(e)}")
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
    
    # Argumentos de línea de comandos
    import argparse
    
    parser = argparse.ArgumentParser(description='ETL Histórico ALSEA')
    parser.add_argument('--fecha-inicio', type=str, default='2024-12-27',
                        help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--fecha-fin', type=str, default=None,
                        help='Fecha de fin (YYYY-MM-DD), default: hoy')
    
    args = parser.parse_args()
    
    run(fecha_inicio=args.fecha_inicio, fecha_fin=args.fecha_fin)
