#!/usr/bin/env python3
"""
ETL Genérico - Creador de nuevos tickers
Genera estructura ETL para cualquier ticker de la BMV
"""
import os
from pathlib import Path


INCREMENTAL_TEMPLATE = '''#!/usr/bin/env python3
"""
ETL Incremental para {TICKER}
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


# Configuración de {TICKER}
TICKER_SYMBOL = "{TICKER_SYMBOL}"
TICKER_ID = None  # Se obtendrá de la BD


def get_ticker_id(loader: SQLServerLoader) -> int:
    """Obtiene el ticker_id de {TICKER} desde la BD"""
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
            raise ValueError(f"Ticker {{TICKER_SYMBOL}} no encontrado en stage.cat_tickers")
    
    finally:
        cursor.close()


def run(lookback_days: int = 1):
    """
    Ejecuta el ETL incremental de {TICKER}
    
    Args:
        lookback_days: Días hacia atrás a cargar (default: 1 = ayer)
    """
    logger.info("=" * 80)
    logger.info(f"ETL INCREMENTAL - {TICKER} - {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}")
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
        logger.info(f"Ticker ID de {{TICKER_SYMBOL}}: {{ticker_id}}")
        
        # Configurar extractor
        extractor = YahooFinanceExtractor(
            ticker_symbol=TICKER_SYMBOL,
            ticker_id=ticker_id
        )
        
        # EXTRACT
        logger.info(f"Extrayendo últimos {{lookback_days}} días de {{TICKER_SYMBOL}}...")
        precios = extractor.extract_incremental(lookback_days=lookback_days)
        
        if not precios:
            logger.warning("No se obtuvieron datos. Finalizando.")
            return
        
        # LOAD
        logger.info(f"Cargando {{len(precios)}} registros a la base de datos...")
        stats = loader.load(precios)
        
        # Resumen
        logger.success("=" * 80)
        logger.success("ETL COMPLETADO EXITOSAMENTE")
        logger.success(f"Insertados: {{stats['inserted']}}")
        logger.success(f"Actualizados: {{stats['updated']}}")
        logger.success(f"Errores: {{stats['errors']}}")
        logger.success("=" * 80)
        
    except Exception as e:
        logger.error(f"Error en ETL incremental: {{str(e)}}")
        raise
    
    finally:
        loader.disconnect()


if __name__ == "__main__":
    # Configurar logging
    logger.remove()  # Remover handler por defecto
    logger.add(
        sys.stdout,
        format="<green>{{time:YYYY-MM-DD HH:mm:ss}}</green> | <level>{{level: <8}}</level> | <cyan>{{name}}</cyan>:<cyan>{{function}}</cyan> - <level>{{message}}</level>",
        level="INFO"
    )
    
    run()
'''


HISTORICAL_TEMPLATE = '''#!/usr/bin/env python3
"""
ETL Histórico para {TICKER}
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


# Configuración de {TICKER}
TICKER_SYMBOL = "{TICKER_SYMBOL}"
TICKER_ID = None  # Se obtendrá de la BD


def get_ticker_id(loader: SQLServerLoader) -> int:
    """Obtiene el ticker_id de {TICKER} desde la BD"""
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
            raise ValueError(f"Ticker {{TICKER_SYMBOL}} no encontrado en stage.cat_tickers")
    
    finally:
        cursor.close()


def run(fecha_inicio: str = "2024-12-27", fecha_fin: str = None):
    """
    Ejecuta el ETL histórico de {TICKER}
    
    Args:
        fecha_inicio: Fecha de inicio en formato YYYY-MM-DD (default: 2024-12-27)
        fecha_fin: Fecha de fin en formato YYYY-MM-DD (default: hoy)
    """
    logger.info("=" * 80)
    logger.info(f"ETL HISTÓRICO - {TICKER} - {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}")
    logger.info("=" * 80)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Parsear fechas
    fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date() if fecha_fin else date.today()
    
    logger.info(f"Rango de carga: {{fecha_inicio_dt}} hasta {{fecha_fin_dt}}")
    
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
        logger.info(f"Ticker ID de {{TICKER_SYMBOL}}: {{ticker_id}}")
        
        # Configurar extractor
        extractor = YahooFinanceExtractor(
            ticker_symbol=TICKER_SYMBOL,
            ticker_id=ticker_id
        )
        
        # EXTRACT
        logger.info(f"Extrayendo datos históricos de {{TICKER_SYMBOL}}...")
        precios = extractor.extract_historical(
            fecha_inicio=fecha_inicio_dt,
            fecha_fin=fecha_fin_dt
        )
        
        if not precios:
            logger.warning("No se obtuvieron datos. Finalizando.")
            return
        
        # LOAD
        logger.info(f"Cargando {{len(precios)}} registros a la base de datos...")
        stats = loader.load(precios, batch_size=100)
        
        # Resumen
        logger.success("=" * 80)
        logger.success("ETL COMPLETADO EXITOSAMENTE")
        logger.success(f"Periodo: {{fecha_inicio_dt}} a {{fecha_fin_dt}}")
        logger.success(f"Insertados: {{stats['inserted']}}")
        logger.success(f"Actualizados: {{stats['updated']}}")
        logger.success(f"Errores: {{stats['errors']}}")
        logger.success("=" * 80)
        
    except Exception as e:
        logger.error(f"Error en ETL histórico: {{str(e)}}")
        raise
    
    finally:
        loader.disconnect()


if __name__ == "__main__":
    # Configurar logging
    logger.remove()  # Remover handler por defecto
    logger.add(
        sys.stdout,
        format="<green>{{time:YYYY-MM-DD HH:mm:ss}}</green> | <level>{{level: <8}}</level> | <cyan>{{name}}</cyan>:<cyan>{{function}}</cyan> - <level>{{message}}</level>",
        level="INFO"
    )
    
    # Argumentos de línea de comandos
    import argparse
    
    parser = argparse.ArgumentParser(description='ETL Histórico {TICKER}')
    parser.add_argument('--fecha-inicio', type=str, default='2024-12-27',
                        help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--fecha-fin', type=str, default=None,
                        help='Fecha de fin (YYYY-MM-DD), default: hoy')
    
    args = parser.parse_args()
    
    run(fecha_inicio=args.fecha_inicio, fecha_fin=args.fecha_fin)
'''


INIT_TEMPLATE = '''"""Módulo ETL para {TICKER}"""
from .incremental import run as run_incremental
from .historical import run as run_historical

__all__ = ['run_incremental', 'run_historical']
'''


def create_ticker_etl(ticker_name: str, ticker_symbol: str):
    """
    Crea estructura ETL para un nuevo ticker
    
    Args:
        ticker_name: Nombre del directorio (ej: walmex, alsea, alfaa)
        ticker_symbol: Símbolo del ticker (ej: WALMEX*, ALSEA*, ALFAA)
    """
    # Crear directorio
    ticker_dir = Path(__file__).parent / "src" / "etl" / ticker_name.lower()
    ticker_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Creando ETL para {ticker_name.upper()}")
    print(f"   Símbolo: {ticker_symbol}")
    print(f"   Directorio: {ticker_dir}")
    
    # Crear __init__.py
    init_file = ticker_dir / "__init__.py"
    with open(init_file, 'w') as f:
        f.write(INIT_TEMPLATE.format(TICKER=ticker_name.upper()))
    print(f"   ✅ {init_file.name}")
    
    # Crear incremental.py
    incr_file = ticker_dir / "incremental.py"
    with open(incr_file, 'w') as f:
        f.write(INCREMENTAL_TEMPLATE.format(
            TICKER=ticker_name.upper(),
            TICKER_SYMBOL=ticker_symbol
        ))
    print(f"   ✅ {incr_file.name}")
    
    # Crear historical.py
    hist_file = ticker_dir / "historical.py"
    with open(hist_file, 'w') as f:
        f.write(HISTORICAL_TEMPLATE.format(
            TICKER=ticker_name.upper(),
            TICKER_SYMBOL=ticker_symbol
        ))
    print(f"   ✅ {hist_file.name}")
    
    print(f"\n💡 Para ejecutar:")
    print(f"   Incremental: python -m src.etl.{ticker_name.lower()}.incremental")
    print(f"   Histórico:   python -m src.etl.{ticker_name.lower()}.historical --fecha-inicio 2024-01-01")
    print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Crear estructura ETL para un nuevo ticker')
    parser.add_argument('ticker_name', type=str, help='Nombre del directorio (ej: alsea)')
    parser.add_argument('ticker_symbol', type=str, help='Símbolo del ticker (ej: ALSEA*)')
    
    args = parser.parse_args()
    
    create_ticker_etl(args.ticker_name, args.ticker_symbol)
