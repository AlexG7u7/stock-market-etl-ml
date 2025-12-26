"""
Script para cargar precios históricos desde DataBursátil a la base de datos
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import argparse

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.databursatil import DataBursatilAPI
from src.db.connection import get_connection
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cargar_precios_ticker(api, conn, ticker_id, simbolo, fecha_inicio, fecha_fin):
    """
    Cargar precios históricos de un ticker específico
    
    Args:
        api: Instancia de DataBursatilAPI
        conn: Conexión a base de datos
        ticker_id: ID del ticker en la base de datos
        simbolo: Símbolo del ticker
        fecha_inicio: Fecha inicial (YYYY-MM-DD)
        fecha_fin: Fecha final (YYYY-MM-DD)
        
    Returns:
        Número de registros insertados
    """
    cursor = conn.cursor()
    
    try:
        # Obtener históricos de la API
        historicos = api.get_historicos(simbolo, fecha_inicio, fecha_fin)
        
        if not historicos:
            logger.warning(f"⚠️  No hay datos para {simbolo}")
            return 0
        
        # Registrar llamada a API
        cursor.execute("""
            INSERT INTO control.api_calls (endpoint, status_code, records_returned)
            VALUES (?, ?, ?)
        """, (f'/v2/historicos?ticker={simbolo}', 200, len(historicos)))
        
        insertados = 0
        actualizados = 0
        
        for precio in historicos:
            # Verificar si existe
            cursor.execute("""
                SELECT precio_id FROM stage.precios_historicos
                WHERE ticker_id = ? AND fecha = ?
            """, (ticker_id, precio['fecha']))
            
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar
                cursor.execute("""
                    UPDATE stage.precios_historicos
                    SET apertura = ?,
                        maximo = ?,
                        minimo = ?,
                        cierre = ?,
                        volumen = ?,
                        fecha_actualizacion = GETDATE()
                    WHERE ticker_id = ? AND fecha = ?
                """, (
                    precio.get('open'),
                    precio.get('high'),
                    precio.get('low'),
                    precio.get('close'),
                    precio.get('volume'),
                    ticker_id,
                    precio['fecha']
                ))
                actualizados += 1
            else:
                # Insertar
                cursor.execute("""
                    INSERT INTO stage.precios_historicos
                    (ticker_id, fecha, apertura, maximo, minimo, cierre, volumen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticker_id,
                    precio['fecha'],
                    precio.get('open'),
                    precio.get('high'),
                    precio.get('low'),
                    precio.get('close'),
                    precio.get('volume')
                ))
                insertados += 1
        
        conn.commit()
        logger.info(f"✅ {simbolo}: {insertados} nuevos, {actualizados} actualizados")
        
        return insertados + actualizados
        
    except Exception as e:
        logger.error(f"❌ Error procesando {simbolo}: {e}")
        conn.rollback()
        return 0
    finally:
        cursor.close()


def cargar_precios(ticker=None, fecha_inicio=None, fecha_fin=None):
    """
    Cargar precios históricos de uno o todos los tickers
    
    Args:
        ticker: Símbolo específico (opcional, None = todos)
        fecha_inicio: Fecha inicial (opcional, default = hace 30 días)
        fecha_fin: Fecha final (opcional, default = hoy)
    """
    # Cargar variables de entorno
    load_dotenv()
    api_token = os.getenv('DATABURSATIL_API_TOKEN')
    
    if not api_token:
        logger.error("❌ DATABURSATIL_API_TOKEN no configurado en .env")
        return False
    
    # Fechas por defecto
    if not fecha_fin:
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
    if not fecha_inicio:
        fecha_inicio = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    logger.info(f"🚀 Iniciando carga de precios históricos...")
    logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
    
    try:
        # Inicializar API
        api = DataBursatilAPI(api_token)
        
        # Conectar a base de datos
        conn = get_connection()
        cursor = conn.cursor()
        
        # Obtener tickers a procesar
        if ticker:
            logger.info(f"🎯 Procesando ticker específico: {ticker}")
            cursor.execute("""
                SELECT ticker_id, simbolo 
                FROM stage.cat_tickers 
                WHERE simbolo = ? AND activo = 1
            """, (ticker,))
        else:
            logger.info("📊 Procesando todos los tickers activos...")
            cursor.execute("""
                SELECT ticker_id, simbolo 
                FROM stage.cat_tickers 
                WHERE activo = 1
                ORDER BY simbolo
            """)
        
        tickers = cursor.fetchall()
        cursor.close()
        
        if not tickers:
            logger.warning(f"⚠️  No se encontraron tickers {'para ' + ticker if ticker else 'activos'}")
            return False
        
        logger.info(f"📈 Procesando {len(tickers)} tickers...")
        
        # Procesar cada ticker
        total_registros = 0
        tickers_exitosos = 0
        tickers_fallidos = 0
        
        for ticker_id, simbolo in tickers:
            registros = cargar_precios_ticker(
                api, conn, ticker_id, simbolo, 
                fecha_inicio, fecha_fin
            )
            
            if registros > 0:
                total_registros += registros
                tickers_exitosos += 1
            else:
                tickers_fallidos += 1
        
        conn.close()
        
        # Resumen
        logger.info("\n" + "="*60)
        logger.info("📊 RESUMEN DE CARGA")
        logger.info("="*60)
        logger.info(f"✅ Tickers procesados exitosamente: {tickers_exitosos}")
        logger.info(f"❌ Tickers sin datos: {tickers_fallidos}")
        logger.info(f"📝 Total de registros cargados: {total_registros}")
        logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
        logger.info("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al cargar precios: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Punto de entrada principal con argumentos CLI"""
    parser = argparse.ArgumentParser(
        description='Cargar precios históricos desde DataBursátil'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        help='Ticker específico (ej: ALFAA). Si se omite, procesa todos.'
    )
    parser.add_argument(
        '--fecha-inicio',
        type=str,
        help='Fecha inicial en formato YYYY-MM-DD (default: hace 30 días)'
    )
    parser.add_argument(
        '--fecha-fin',
        type=str,
        help='Fecha final en formato YYYY-MM-DD (default: hoy)'
    )
    
    args = parser.parse_args()
    
    exito = cargar_precios(
        ticker=args.ticker,
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin
    )
    
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
