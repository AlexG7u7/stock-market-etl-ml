"""
Script para ejecutar ETL incremental usando API de DataBursátil
Carga cotizaciones del día actual (datos más recientes) de los tickers configurados
Usa el endpoint /v2/cotizaciones para obtener precios actuales
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import argparse
import yaml

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.databursatil import DataBursatilAPI
from src.db.connection import get_connection
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_config():
    """Cargar configuración desde YAML"""
    config_path = project_root / 'config' / 'tickers_config.yml'
    
    if not config_path.exists():
        logger.error(f"❌ Archivo de configuración no encontrado: {config_path}")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"✅ Configuración cargada desde {config_path}")
    return config


def cargar_precios_ticker_databursatil(
    ticker_id: int,
    emisora_serie: str,
    fecha_inicio: str,
    fecha_fin: str,
    api: DataBursatilAPI,
    cursor,
    log_id: int
) -> tuple:
    """
    Cargar precios de un ticker desde DataBursátil API
    
    Args:
        ticker_id: ID del ticker en la base de datos
        emisora_serie: Código del ticker (ej: 'ALFAA')
        fecha_inicio: Fecha inicial (YYYY-MM-DD) - no usado en cotizaciones
        fecha_fin: Fecha final (YYYY-MM-DD) - no usado en cotizaciones
        api: Instancia de DataBursatilAPI
        cursor: Cursor de base de datos
        log_id: ID del log de ETL
        
    Returns:
        (registros_insertados, registros_actualizados, errores)
    """
    try:
        # Obtener cotización actual desde DataBursátil
        # La API de cotizaciones devuelve solo el dato más reciente
        data = api.get_cotizaciones(emisora_serie=emisora_serie, bolsa="BMV")
        
        # DEBUG: Ver respuesta completa
        logger.info(f"  🔍 Respuesta API: {data}")
        
        # Verificar si hay error
        if 'Error' in data:
            logger.warning(f"⚠️  Error en API: {data.get('Error')}")
            return 0, 0, 1
        
        # La respuesta es: {"ALFAA": {"bolsa": "BMV", "u": 15.50, ...}}
        ticker_data = data.get(emisora_serie)
        
        if not ticker_data:
            logger.warning(f"⚠️  No hay datos para {emisora_serie}")
            logger.info(f"  🔍 Keys en respuesta: {list(data.keys())}")
            return 0, 0, 0
        
        # DEBUG: Ver datos del ticker
        logger.info(f"  🔍 Datos del ticker: {ticker_data}")
        
        # Extraer datos de la cotización
        fecha = ticker_data.get('f')  # fecha
        
        if not fecha:
            logger.warning(f"⚠️  No hay fecha en la respuesta para {emisora_serie}")
            return 0, 0, 0
        
        # Mapear campos según documentación DataBursátil
        precio_ultimo = ticker_data.get('u')      # último
        precio_anterior = ticker_data.get('a')    # anterior
        precio_maximo = ticker_data.get('x')      # máximo
        precio_minimo = ticker_data.get('n')      # mínimo
        volumen = ticker_data.get('v')            # volumen
        importe = ticker_data.get('i')            # importe
        
        if precio_ultimo is None:
            logger.warning(f"⚠️  No hay precio último para {emisora_serie}")
            return 0, 0, 0
        
        # Verificar si ya existe el registro
        cursor.execute("""
            SELECT COUNT(*) 
            FROM stage.precios_historicos
            WHERE ticker_id = ? AND fecha = ?
        """, (ticker_id, fecha))
        
        existe = cursor.fetchval() > 0
        
        if existe:
            # Actualizar registro existente
            cursor.execute("""
                UPDATE stage.precios_historicos
                SET 
                    [open] = ?,
                    [high] = ?,
                    [low] = ?,
                    [close] = ?,
                    volume = ?,
                    importe = ?,
                    fecha_carga = GETDATE()
                WHERE ticker_id = ? AND fecha = ?
            """, (precio_anterior, precio_maximo, precio_minimo, precio_ultimo, 
                  volumen, importe, ticker_id, fecha))
            
            logger.info(f"  🔄 Actualizado: {emisora_serie} - {fecha} - Cierre: ${precio_ultimo}")
            return 0, 1, 0
        else:
            # Insertar nuevo registro
            cursor.execute("""
                INSERT INTO stage.precios_historicos
                (ticker_id, fecha, [open], [high], [low], [close], volume, importe)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticker_id, fecha, precio_anterior, precio_maximo, precio_minimo, 
                  precio_ultimo, volumen, importe))
            
            logger.info(f"  � Insertado: {emisora_serie} - {fecha} - Cierre: ${precio_ultimo}")
            return 1, 0, 0
        
    except Exception as e:
        logger.error(f"  ❌ Error procesando {emisora_serie}: {e}")
        return 0, 0, 1


def ejecutar_etl_incremental_databursatil(config, fecha_inicio=None, fecha_fin=None):
    """
    Ejecutar ETL incremental usando DataBursátil API
    
    Args:
        config: Configuración cargada desde YAML
        fecha_inicio: Fecha inicio opcional (override)
        fecha_fin: Fecha fin opcional (override)
    """
    # Cargar variables de entorno
    env_file = project_root / '.env'
    if not env_file.exists():
        logger.error("❌ Archivo .env no encontrado")
        return False
    
    load_dotenv(env_file)
    
    api_token = os.getenv('DATABURSATIL_API_TOKEN')
    if not api_token:
        logger.error("❌ Variable DATABURSATIL_API_TOKEN no encontrada en .env")
        return False
    
    tickers_activos = config.get('tickers_activos', [])
    
    if not tickers_activos:
        logger.warning("⚠️  No hay tickers activos configurados")
        return False
    
    # Determinar fechas
    if not fecha_fin:
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    if not fecha_inicio:
        # Por defecto, traer solo el día actual o días hábiles recientes
        lookback = config.get('incremental', {}).get('lookback_days', 1)
        fecha_inicio = (datetime.now() - timedelta(days=lookback)).strftime('%Y-%m-%d')
    
    logger.info(f"🚀 ETL Incremental DataBursátil - {len(tickers_activos)} tickers activos")
    logger.info(f"📅 Rango: {fecha_inicio} a {fecha_fin}")
    logger.info(f"📊 Tickers: {', '.join(tickers_activos)}")
    
    proceso_inicio = datetime.now()
    log_id = None
    
    try:
        # Inicializar API de DataBursátil
        api = DataBursatilAPI(api_token)
        
        # Conectar a base de datos
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Registrar inicio en control.etl_log
            cursor.execute("""
                INSERT INTO control.etl_log 
                (proceso, estado, fecha_inicio)
                VALUES (?, ?, ?)
            """, ('etl_incremental_databursatil', 'EN PROCESO', proceso_inicio))
            log_id = cursor.execute("SELECT @@IDENTITY").fetchval()
            conn.commit()
            
            # Obtener información de tickers desde DB
            exitosos = 0
            fallidos = 0
            total_insertados = 0
            total_actualizados = 0
            
            for idx, ticker in enumerate(tickers_activos, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"[{idx}/{len(tickers_activos)}] Procesando {ticker}")
                logger.info(f"{'='*60}")
                
                # Buscar ticker_id en la base de datos
                cursor.execute("""
                    SELECT ticker_id, emisora_serie
                    FROM stage.cat_tickers
                    WHERE emisora_serie = ?
                """, (ticker,))
                
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"⚠️  Ticker {ticker} no encontrado en cat_tickers")
                    fallidos += 1
                    continue
                
                ticker_id, emisora_serie = row
                
                try:
                    insertados, actualizados, errores = cargar_precios_ticker_databursatil(
                        ticker_id=ticker_id,
                        emisora_serie=emisora_serie,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        api=api,
                        cursor=cursor,
                        log_id=log_id
                    )
                    
                    total_insertados += insertados
                    total_actualizados += actualizados
                    
                    if insertados > 0 or actualizados > 0:
                        exitosos += 1
                        logger.info(f"✅ {ticker} completado")
                        conn.commit()
                    else:
                        fallidos += 1
                        logger.warning(f"⚠️  {ticker} sin datos")
                        
                except Exception as e:
                    fallidos += 1
                    logger.error(f"❌ Error procesando {ticker}: {e}")
                    conn.rollback()
            
            # Actualizar log final
            cursor.execute("""
                UPDATE control.etl_log
                SET 
                    estado = ?,
                    fecha_fin = ?,
                    registros_procesados = ?,
                    mensaje = ?
                WHERE log_id = ?
            """, (
                'COMPLETADO' if fallidos == 0 else 'ERROR',
                datetime.now(),
                total_insertados + total_actualizados,
                f"Insertados: {total_insertados}, Actualizados: {total_actualizados}, Exitosos: {exitosos}, Fallidos: {fallidos}",
                log_id
            ))
            conn.commit()
            
            # Resumen final
            logger.info(f"\n{'='*60}")
            logger.info("📊 RESUMEN FINAL")
            logger.info(f"{'='*60}")
            logger.info(f"Total tickers: {len(tickers_activos)}")
            logger.info(f"✅ Exitosos: {exitosos}")
            logger.info(f"❌ Fallidos: {fallidos}")
            logger.info(f"📥 Insertados: {total_insertados}")
            logger.info(f"🔄 Actualizados: {total_actualizados}")
            logger.info(f"📅 Período: {fecha_inicio} a {fecha_fin}")
            logger.info(f"⏱️  Tiempo: {(datetime.now() - proceso_inicio).total_seconds():.1f}s")
            logger.info(f"{'='*60}")
            
            return fallidos == 0
            
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        
        if log_id:
            try:
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE control.etl_log
                        SET estado = ?, fecha_fin = ?, mensaje_error = ?
                        WHERE log_id = ?
                    """, ('ERROR', datetime.now(), str(e), log_id))
                    conn.commit()
            except:
                pass
        
        return False


def main():
    """Punto de entrada principal"""
    parser = argparse.ArgumentParser(
        description='ETL Incremental usando DataBursátil API'
    )
    parser.add_argument(
        '--fecha-inicio',
        type=str,
        help='Fecha inicial (YYYY-MM-DD). Si no se especifica, usa lookback_days de config'
    )
    parser.add_argument(
        '--fecha-fin',
        type=str,
        help='Fecha final (YYYY-MM-DD). Si no se especifica, usa hoy'
    )
    
    args = parser.parse_args()
    
    # Cargar configuración
    config = load_config()
    if not config:
        logger.error("❌ No se pudo cargar la configuración")
        sys.exit(1)
    
    # Ejecutar ETL
    exito = ejecutar_etl_incremental_databursatil(
        config,
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin
    )
    
    sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
