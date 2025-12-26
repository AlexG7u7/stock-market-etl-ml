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
    
    # Cargar variables de entorno desde .env si existe (útil para desarrollo local)
    # En producción, los workflows de GitHub Actions pasan las variables directamente
    env_file = project_root / '.env'
    if env_file.exists():
        load_dotenv(env_file)
    
    api_token = os.getenv('DATABURSATIL_API_TOKEN')
    
    if not api_token:
        logger.error("❌ DATABURSATIL_API_TOKEN no configurado")
        logger.error("   Configura la variable de entorno o crea un archivo .env en la raíz del proyecto")
        return False
    
    try:
        # Inicializar API
        logger.info("🚀 Iniciando carga de tickers...")
        api = DataBursatilAPI(api_token)
        
        # Obtener emisoras de la API
        emisoras = api.get_emisoras()
        logger.info(f"📥 Obtenidas {len(emisoras)} emisoras de la API")
        
        # Conectar a base de datos
        conn = get_connection()
        cursor = conn.cursor()
        
        # Registrar llamada a API
        cursor.execute("""
            INSERT INTO control.api_calls (endpoint, status_code, records_returned)
            VALUES (?, ?, ?)
        """, ('/v2/emisoras', 200, len(emisoras)))
        
        # Insertar/actualizar tickers
        insertados = 0
        actualizados = 0
        
        for emisora in emisoras:
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
        conn.commit()
        
        logger.info(f"✅ Carga completada:")
        logger.info(f"   📝 {insertados} tickers nuevos")
        logger.info(f"   🔄 {actualizados} tickers actualizados")
        logger.info(f"   📊 Total: {insertados + actualizados} tickers en catálogo")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al cargar tickers: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    exito = cargar_tickers()
    sys.exit(0 if exito else 1)
