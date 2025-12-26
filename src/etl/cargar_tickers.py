"""
Script para cargar el catálogo de tickers desde DataBursátil a la base de datos
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import logging

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


def cargar_tickers():
    """Cargar catálogo de tickers desde API a base de datos"""
    
    logger.info("="*60)
    logger.info("🚀 INICIANDO PROCESO DE CARGA DE TICKERS")
    logger.info("="*60)
    
    # Cargar variables de entorno desde .env si existe (útil para desarrollo local)
    # En producción, los workflows de GitHub Actions pasan las variables directamente
    env_file = project_root / '.env'
    logger.info(f"📁 Ruta proyecto: {project_root}")
    logger.info(f"📄 Buscando .env en: {env_file}")
    
    if env_file.exists():
        logger.info("✅ Archivo .env encontrado, cargando...")
        load_dotenv(env_file)
    else:
        logger.info("ℹ️  No hay archivo .env, usando variables de entorno del sistema")
    
    api_token = os.getenv('DATABURSATIL_API_TOKEN')
    sql_server = os.getenv('SQL_SERVER', 'NO_CONFIGURADO')
    sql_database = os.getenv('SQL_DATABASE', 'NO_CONFIGURADO')
    sql_user = os.getenv('SQL_USER', 'NO_CONFIGURADO')
    
    logger.info(f"🔑 DATABURSATIL_API_TOKEN: {'✅ Configurado (' + api_token[:10] + '...)' if api_token else '❌ NO CONFIGURADO'}")
    logger.info(f"🗄️  SQL_SERVER: {sql_server}")
    logger.info(f"🗄️  SQL_DATABASE: {sql_database}")
    logger.info(f"👤 SQL_USER: {sql_user}")
    
    if not api_token:
        logger.error("❌ DATABURSATIL_API_TOKEN no configurado")
        logger.error("   Configura la variable de entorno o crea un archivo .env en la raíz del proyecto")
        return False
    
    try:
        # Inicializar API
        logger.info("-"*60)
        logger.info("� Inicializando cliente API...")
        api = DataBursatilAPI(api_token)
        
        # Obtener emisoras de la API
        logger.info("📡 Llamando a API para obtener emisoras...")
        emisoras = api.get_emisoras()
        logger.info(f"✅ Obtenidas {len(emisoras)} emisoras de la API")
        
        if len(emisoras) > 0:
            logger.info(f"📋 Ejemplo de emisora: {emisoras[0]}")
        else:
            logger.warning("⚠️  La API no devolvió emisoras!")
            return False
        
        # Conectar a base de datos
        logger.info("-"*60)
        logger.info("💾 Conectando a base de datos...")
        conn = get_connection()
        cursor = conn.cursor()
        logger.info("✅ Conexión a BD establecida")
        
        # Registrar llamada a API
        logger.info("📝 Registrando llamada en control.api_calls...")
        cursor.execute("""
            INSERT INTO control.api_calls (endpoint, status_code, records_returned)
            VALUES (?, ?, ?)
        """, ('/v2/emisoras', 200, len(emisoras)))
        logger.info("✅ Llamada API registrada")
        
        # Insertar/actualizar tickers
        logger.info("-"*60)
        logger.info("💾 Procesando emisoras...")
        insertados = 0
        actualizados = 0
        
        for idx, emisora in enumerate(emisoras, 1):
            if idx % 10 == 0:
                logger.info(f"   Procesando {idx}/{len(emisoras)}...")
            
            # Verificar si existe
            cursor.execute("""
                SELECT ticker_id FROM stage.cat_tickers 
                WHERE simbolo = ?
            """, (emisora['symbol'],))
            
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar
                cursor.execute("""
                    UPDATE stage.cat_tickers
                    SET nombre_empresa = ?,
                        sector = ?,
                        isin = ?,
                        tipo_valor = ?,
                        activo = 1,
                        fecha_actualizacion = GETDATE()
                    WHERE simbolo = ?
                """, (
                    emisora.get('name'),
                    emisora.get('sector'),
                    emisora.get('isin'),
                    emisora.get('tipo_valor'),
                    emisora['symbol']
                ))
                actualizados += 1
            else:
                # Insertar
                cursor.execute("""
                    INSERT INTO stage.cat_tickers 
                    (simbolo, nombre_empresa, sector, isin, tipo_valor, activo)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (
                    emisora['symbol'],
                    emisora.get('name'),
                    emisora.get('sector'),
                    emisora.get('isin'),
                    emisora.get('tipo_valor')
                ))
                insertados += 1
        
        # Commit
        logger.info("-"*60)
        logger.info("💾 Guardando cambios en base de datos...")
        conn.commit()
        logger.info("✅ Commit exitoso")
        
        # Registrar en log de ETL
        cursor.execute("""
            INSERT INTO control.etl_log 
            (etl_process, status, records_processed, mensaje)
            VALUES (?, ?, ?, ?)
        """, (
            'cargar_tickers',
            'SUCCESS',
            insertados + actualizados,
            f'{insertados} nuevos, {actualizados} actualizados'
        ))
        conn.commit()
        
        logger.info("="*60)
        logger.info(f"✅ CARGA COMPLETADA EXITOSAMENTE")
        logger.info(f"   📝 {insertados} tickers nuevos")
        logger.info(f"   🔄 {actualizados} tickers actualizados")
        logger.info(f"   📊 Total procesado: {insertados + actualizados}")
        logger.info("="*60)
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error("="*60)
        logger.error(f"❌ ERROR AL CARGAR TICKERS")
        logger.error("="*60)
        logger.error(f"Tipo de error: {type(e).__name__}")
        logger.error(f"Mensaje: {e}")
        logger.error("-"*60)
        logger.error("Stack trace completo:")
        import traceback
        traceback.print_exc()
        logger.error("="*60)
        
        # Intentar registrar el error en BD
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO control.etl_log 
                (etl_process, status, records_processed, mensaje)
                VALUES (?, ?, ?, ?)
            """, (
                'cargar_tickers',
                'ERROR',
                0,
                str(e)[:500]  # Limitar mensaje a 500 chars
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except:
            logger.error("No se pudo registrar el error en control.etl_log")
        
        return False


if __name__ == "__main__":
    exito = cargar_tickers()
    sys.exit(0 if exito else 1)
