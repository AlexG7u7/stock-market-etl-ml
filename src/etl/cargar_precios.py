"""
ETL para cargar precios históricos OHLCV usando Yahoo Finance
Uso:
    python src/etl/cargar_precios.py --ticker ALFAA --fecha-inicio 2024-01-01 --fecha-fin 2024-12-31
    python src/etl/cargar_precios.py --todos --fecha-inicio 2024-01-01 --fecha-fin 2024-12-31 --limite 10
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import argparse
import codecs
import time

# Configurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.yahoo_finance import YahooFinanceAPI
from src.db.connection import get_connection
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def cargar_precios_ticker(
    ticker_id: int,
    emisora_serie: str,
    fecha_inicio: str,
    fecha_fin: str,
    api: YahooFinanceAPI,
    cursor
) -> tuple:
    """
    Cargar precios históricos OHLCV de un ticker desde Yahoo Finance
    
    Args:
        ticker_id: ID del ticker en la BD
        emisora_serie: Símbolo del ticker (ej: 'ALFAA')
        fecha_inicio: Fecha inicio en formato YYYY-MM-DD
        fecha_fin: Fecha fin en formato YYYY-MM-DD
        api: Cliente de Yahoo Finance
        cursor: Cursor de BD
        
    Returns:
        Tuple (insertados, actualizados, errores)
    """
    logger.info(f"📊 Procesando {emisora_serie} ({fecha_inicio} a {fecha_fin})")
    
    try:
        # Obtener datos históricos de Yahoo Finance
        historicos = api.get_historicos(
            ticker=emisora_serie,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        if not historicos:
            logger.warning(f"⚠️  No se obtuvieron datos para {emisora_serie}")
            return (0, 0, 0)
        
        insertados = 0
        actualizados = 0
        errores = 0
        
        for precio in historicos:
            try:
                fecha = precio.get('fecha')
                
                # Verificar si ya existe
                cursor.execute("""
                    SELECT precio_id FROM stage.precios_historicos
                    WHERE ticker_id = ? AND fecha = ?
                """, (ticker_id, fecha))
                
                existe = cursor.fetchone()
                
                if existe:
                    # Actualizar
                    cursor.execute("""
                        UPDATE stage.precios_historicos
                        SET [open] = ?,
                            [high] = ?,
                            [low] = ?,
                            [close] = ?,
                            volume = ?,
                            close_ajustado = ?
                        WHERE ticker_id = ? AND fecha = ?
                    """, (
                        precio.get('open'),
                        precio.get('high'),
                        precio.get('low'),
                        precio.get('close'),
                        precio.get('volume'),
                        precio.get('close'),  # Yahoo ya devuelve precio ajustado
                        ticker_id,
                        fecha
                    ))
                    actualizados += 1
                else:
                    # Insertar
                    cursor.execute("""
                        INSERT INTO stage.precios_historicos
                        (ticker_id, fecha, [open], [high], [low], [close], volume, close_ajustado)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ticker_id,
                        fecha,
                        precio.get('open'),
                        precio.get('high'),
                        precio.get('low'),
                        precio.get('close'),
                        precio.get('volume'),
                        precio.get('close')  # Yahoo ya devuelve precio ajustado
                    ))
                    insertados += 1
                    
            except Exception as e:
                logger.error(f"Error procesando precio {fecha}: {e}")
                errores += 1
        
        logger.info(f"✅ {emisora_serie}: {insertados} insertados, {actualizados} actualizados, {errores} errores")
        return (insertados, actualizados, errores)
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo datos de {emisora_serie}: {e}")
        return (0, 0, 1)


def cargar_precios(ticker=None, fecha_inicio=None, fecha_fin=None, limite=None, todos=False):
    """
    Cargar precios históricos de uno o todos los tickers
    
    Args:
        ticker: Emisora-Serie específica (opcional, ej: 'ALFAA')
        fecha_inicio: Fecha inicial (opcional, default = hace 365 días)
        fecha_fin: Fecha final (opcional, default = hoy)
        limite: Límite de tickers a procesar (opcional, para testing)
        todos: Si True, procesa todos los tickers (ignora ticker específico)
    """
    # Cargar variables de entorno desde .env si existe
    env_file = project_root / '.env'
    if env_file.exists():
        load_dotenv(env_file)
    
    # Fechas por defecto
    if not fecha_fin:
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
    if not fecha_inicio:
        fecha_inicio = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    logger.info(f"🚀 Iniciando carga de precios históricos...")
    logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
    
    proceso_inicio = datetime.now()
    
    try:
        # Inicializar API de Yahoo Finance
        api = YahooFinanceAPI()
        
        # Conectar a base de datos
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Registrar inicio en control.etl_log
            cursor.execute("""
                INSERT INTO control.etl_log 
                (proceso, estado, fecha_inicio)
                VALUES (?, ?, ?)
            """, ('cargar_precios', 'EN PROCESO', proceso_inicio))
            etl_log_id = cursor.execute("SELECT @@IDENTITY").fetchval()
            conn.commit()
            
            # Obtener tickers a procesar
            if ticker and not todos:
                logger.info(f"🎯 Procesando ticker específico: {ticker}")
                cursor.execute("""
                    SELECT ticker_id, emisora_serie
                    FROM stage.cat_tickers 
                    WHERE emisora_serie = ?
                """, (ticker,))
            else:
                logger.info("📊 Procesando todos los tickers activos...")
                if limite:
                    logger.info(f"   Límite: {limite} tickers")
                    cursor.execute("""
                        SELECT TOP (?) ticker_id, emisora_serie
                        FROM stage.cat_tickers 
                        ORDER BY emisora_serie
                    """, (limite,))
                else:
                    cursor.execute("""
                        SELECT ticker_id, emisora_serie
                        FROM stage.cat_tickers 
                        ORDER BY emisora_serie
                    """)
            
            tickers = cursor.fetchall()
            
            if not tickers:
                logger.warning(f"⚠️  No se encontraron tickers {'para ' + ticker if ticker else 'activos'}")
                cursor.execute("""
                    UPDATE control.etl_log
                    SET estado = ?, fecha_fin = ?, registros_procesados = 0
                    WHERE etl_log_id = ?
                """, ('COMPLETADO', datetime.now(), etl_log_id))
                conn.commit()
                return False
            
            logger.info(f"📈 {len(tickers)} tickers a procesar")
            
            # Procesar cada ticker
            total_insertados = 0
            total_actualizados = 0
            total_errores = 0
            tickers_exitosos = 0
            tickers_fallidos = 0
            
            for idx, (ticker_id, emisora_serie) in enumerate(tickers, 1):
                logger.info(f"\n[{idx}/{len(tickers)}] {emisora_serie}")
                
                insertados, actualizados, errores = cargar_precios_ticker(
                    ticker_id, 
                    emisora_serie, 
                    fecha_inicio, 
                    fecha_fin, 
                    api, 
                    cursor
                )
                
                total_insertados += insertados
                total_actualizados += actualizados
                total_errores += errores
                
                if insertados > 0 or actualizados > 0:
                    tickers_exitosos += 1
                else:
                    tickers_fallidos += 1
                
                # Commit cada ticker para no perder datos en caso de error
                try:
                    conn.commit()
                except Exception as e:
                    logger.error(f"Error en commit: {e}")
                    conn.rollback()
                
                # Pequeña pausa para no saturar Yahoo Finance
                if idx % 10 == 0:
                    time.sleep(1)
            
            # Actualizar log final
            proceso_fin = datetime.now()
            total_registros = total_insertados + total_actualizados
            
            cursor.execute("""
                UPDATE control.etl_log
                SET estado = ?,
                    fecha_fin = ?,
                    registros_procesados = ?
                WHERE etl_log_id = ?
            """, ('COMPLETADO', proceso_fin, total_registros, etl_log_id))
            
            conn.commit()
            
            # Resumen final
            duracion = (proceso_fin - proceso_inicio).total_seconds()
            logger.info("\n" + "="*60)
            logger.info("📊 RESUMEN DE CARGA")
            logger.info("="*60)
            logger.info(f"✅ Tickers exitosos: {tickers_exitosos}")
            logger.info(f"❌ Tickers sin datos: {tickers_fallidos}")
            logger.info(f"📝 Total insertados: {total_insertados}")
            logger.info(f"🔄 Total actualizados: {total_actualizados}")
            logger.info(f"⚠️  Total errores: {total_errores}")
            logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
            logger.info(f"⏱️  Duración: {duracion:.1f} segundos")
            logger.info("="*60)
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Error al cargar precios: {e}")
        import traceback
        traceback.print_exc()
        
        # Actualizar log como error
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE control.etl_log
                    SET estado = ?, fecha_fin = ?
                    WHERE etl_log_id = ?
                """, ('ERROR', datetime.now(), etl_log_id))
                conn.commit()
        except:
            pass
        
        return False


def main():
    """Punto de entrada principal con argumentos CLI"""
    parser = argparse.ArgumentParser(
        description='Cargar precios históricos OHLCV desde Yahoo Finance'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        help='Ticker específico (ej: ALFAA). Si se omite, usa --todos.'
    )
    parser.add_argument(
        '--todos',
        action='store_true',
        help='Procesar todos los tickers en stage.cat_tickers'
    )
    parser.add_argument(
        '--fecha-inicio',
        type=str,
        help='Fecha inicial en formato YYYY-MM-DD (default: hace 365 días)'
    )
    parser.add_argument(
        '--fecha-fin',
        type=str,
        help='Fecha final en formato YYYY-MM-DD (default: hoy)'
    )
    parser.add_argument(
        '--limite',
        type=int,
        help='Limitar número de tickers a procesar (útil para testing)'
    )
    
    args = parser.parse_args()
    
    # Validar argumentos
    if not args.ticker and not args.todos:
        logger.error("❌ Debe especificar --ticker o --todos")
        parser.print_help()
        sys.exit(1)
    
    exito = cargar_precios(
        ticker=args.ticker,
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin,
        limite=args.limite,
        todos=args.todos
    )
    
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
