"""
Script de inicialización de base de datos SQL Server.
Ejecuta los scripts SQL para crear el esquema completo.
"""

import sys
from pathlib import Path
import subprocess

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import Config
from src.utils.logger import get_logger
from src.db.connection import SQLServerConnection

logger = get_logger("setup_db")


def execute_sql_file(conn: SQLServerConnection, sql_file: Path):
    """
    Ejecuta un archivo SQL.
    
    Args:
        conn: Conexión activa a SQL Server
        sql_file: Ruta al archivo SQL
    """
    logger.info(f"📄 Ejecutando: {sql_file.name}")
    
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Dividir por GO (separador de lotes en SQL Server)
        batches = sql_script.split('GO')
        
        for i, batch in enumerate(batches, 1):
            batch = batch.strip()
            if batch and not batch.startswith('--'):
                try:
                    conn.execute_query(batch)
                    logger.debug(f"  ✅ Lote {i}/{len(batches)} ejecutado")
                except Exception as e:
                    # Algunos comandos pueden fallar si ya existen (no crítico)
                    if "already exists" in str(e).lower():
                        logger.debug(f"  ⚠️  Lote {i}: ya existe (ignorado)")
                    else:
                        logger.error(f"  ❌ Error en lote {i}: {e}")
                        raise
        
        logger.info(f"✅ {sql_file.name} ejecutado exitosamente")
        
    except Exception as e:
        logger.error(f"❌ Error ejecutando {sql_file.name}: {e}")
        raise


def setup_database():
    """Inicializa la base de datos con el esquema completo."""
    
    logger.info("=" * 70)
    logger.info("INICIALIZACIÓN DE BASE DE DATOS SQL SERVER")
    logger.info("=" * 70)
    
    # Validar configuración
    if not Config.validate():
        logger.error("❌ Configuración inválida. Revisa tu archivo .env")
        return False
    
    # Directorio de scripts SQL
    sql_dir = Config.BASE_DIR / "sql"
    
    if not sql_dir.exists():
        logger.error(f"❌ Directorio SQL no encontrado: {sql_dir}")
        return False
    
    # Scripts a ejecutar en orden
    sql_scripts = [
        "01_create_schema.sql",
        "02_create_indexes.sql",
        "03_stored_procedures.sql",
    ]
    
    try:
        # Conectar a SQL Server
        logger.info("\n🔐 Conectando a SQL Server...")
        conn = SQLServerConnection(use_sqlalchemy=False)
        
        if not conn.test_connection():
            logger.error("❌ No se pudo conectar a SQL Server")
            return False
        
        logger.info("✅ Conexión establecida\n")
        
        # Ejecutar scripts
        for script_name in sql_scripts:
            script_path = sql_dir / script_name
            
            if not script_path.exists():
                logger.warning(f"⚠️  Script no encontrado: {script_name}")
                continue
            
            execute_sql_file(conn, script_path)
            print()  # Línea en blanco
        
        # Verificar tablas creadas
        logger.info("📊 Verificando tablas creadas...")
        query = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        
        df = conn.read_sql(query)
        
        if not df.empty:
            logger.info(f"✅ {len(df)} tablas creadas:")
            for idx, row in df.iterrows():
                logger.info(f"   - {row['TABLE_NAME']}")
        else:
            logger.warning("⚠️  No se encontraron tablas")
        
        # Cerrar conexión
        conn.close()
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ BASE DE DATOS INICIALIZADA EXITOSAMENTE")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Error durante inicialización: {e}")
        return False


def main():
    """Función principal."""
    
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "SETUP BASE DE DATOS SQL SERVER" + " " * 23 + "║")
    print("║" + " " * 20 + "Proyecto ETL Bursátil" + " " * 27 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    # Confirmar ejecución
    respuesta = input("¿Deseas inicializar la base de datos? (s/N): ").strip().lower()
    
    if respuesta not in ['s', 'si', 'sí', 'y', 'yes']:
        print("\n❌ Operación cancelada por el usuario")
        return
    
    print()
    
    # Ejecutar setup
    success = setup_database()
    
    if success:
        print("\n🎉 ¡Base de datos lista para usar!")
        print("\n📝 Próximos pasos:")
        print("   1. Ejecutar notebook: notebooks/01_etl_historico.ipynb")
        print("   2. O ejecutar script: python scripts/run_etl_historico.py")
    else:
        print("\n❌ Hubo errores durante la inicialización")
        print("   Revisa los logs para más detalles")
        sys.exit(1)


if __name__ == "__main__":
    main()
