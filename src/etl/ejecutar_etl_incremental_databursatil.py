"""
Script para ejecutar ETL incremental usando API de DataBursátil
Carga datos del día actual de los tickers configurados
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
        fecha_inicio: Fecha inicial (YYYY-MM-DD)
        fecha_fin: Fecha final (YYYY-MM-DD)
        api: Instancia de DataBursatilAPI
        cursor: Cursor de base de datos
        log_id: ID del log de ETL
        
    Returns:
        (registros_insertados, registros_actualizados, errores)
    """
    try:
        # Obtener históricos desde DataBursátil
        historicos = api.get_historicos(
            emisora_serie=emisora_serie,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin
        )
        
        if not historicos:
            logger.warning(f"⚠️  No hay datos para {emisora_serie}")
            return 0, 0, 0
        
        insertados = 0
        actualizados = 0
        
        # Procesar cada registro
        for registro in historicos:
            fecha = registro.get('fecha')
            precio = registro.get('precio')  # Precio de cierre
            importe = registro.get('importe')
            
            if not fecha or precio is None:
                continue
            
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
                        precio_cierre = ?,
                        volumen = ?,
                        fecha_actualizacion = GETDATE(),
                        fuente = 'databursatil',
                        log_id = ?
                    WHERE ticker_id = ? AND fecha = ?
                """, (precio, importe, log_id, ticker_id, fecha))
                actualizados += 1
            else:
                # Insertar nuevo registro
                # DataBursátil solo da precio de cierre, usamos el mismo para apertura/alto/bajo
                cursor.execute("""
                    INSERT INTO stage.precios_historicos
                    (ticker_id, fecha, precio_apertura, precio_maximo, precio_minimo, 
                     precio_cierre, volumen, fuente, log_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'databursatil', ?)
                """, (ticker_id, fecha, precio, precio, precio, precio, importe, log_id))
                insertados += 1
        
        logger.info(f"  📊 Insertados: {insertados} | Actualizados: {actualizados}")
        return insertados, actualizados, 0
        
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
                'COMPLETADO' if fallidos == 0 else 'COMPLETADO_CON_ERRORES',
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
