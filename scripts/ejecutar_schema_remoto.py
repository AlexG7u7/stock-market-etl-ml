"""
Script para ejecutar 01_create_schema.sql en SQL Server remoto
"""
import pyodbc
import os
from pathlib import Path

# Configuración
SQL_SERVER_HOST = 'localhost'  # o la IP/hostname del servidor
SQL_SERVER_USER = 'rodrigo'
SQL_SERVER_PASSWORD = input("Ingresa la contraseña de SQL Server: ")
SQL_SCRIPT_PATH = Path(__file__).parent.parent / 'sql' / '01_create_schema.sql'

def ejecutar_script_sql():
    """Ejecuta el script SQL en el servidor"""
    
    # Leer el script
    with open(SQL_SCRIPT_PATH, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # Dividir por GO (SQL Server batch separator)
    batches = [batch.strip() for batch in sql_script.split('GO') if batch.strip()]
    
    try:
        # Conectar a SQL Server
        conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={SQL_SERVER_HOST};'
            f'UID={SQL_SERVER_USER};'
            f'PWD={SQL_SERVER_PASSWORD};'
            f'TrustServerCertificate=yes;'
        )
        
        print(f"Conectando a SQL Server en {SQL_SERVER_HOST}...")
        conn = pyodbc.connect(conn_str, autocommit=True)
        cursor = conn.cursor()
        
        print(f"\n{'='*60}")
        print(f"Ejecutando script: {SQL_SCRIPT_PATH.name}")
        print(f"Total de batches: {len(batches)}")
        print(f"{'='*60}\n")
        
        # Ejecutar cada batch
        for i, batch in enumerate(batches, 1):
            print(f"[{i}/{len(batches)}] Ejecutando batch...")
            try:
                cursor.execute(batch)
                
                # Mostrar resultados si los hay
                if cursor.description:
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"  → {row[0]}")
                
            except pyodbc.Error as e:
                print(f"  ⚠️  Error en batch {i}: {e}")
                continue
        
        print(f"\n{'='*60}")
        print("✅ Script ejecutado exitosamente")
        print(f"{'='*60}\n")
        
        # Verificar tablas creadas
        cursor.execute("""
            SELECT 
                SCHEMA_NAME(schema_id) as schema_name,
                name as table_name
            FROM sys.tables
            WHERE name IN (
                'api_calls', 'etl_log', 
                'cat_tickers', 'cat_calendario', 
                'precios_historicos', 'indicadores_tecnicos', 'retornos'
            )
            ORDER BY schema_name, name
        """)
        
        print("\n📊 Tablas creadas:")
        for row in cursor.fetchall():
            print(f"  ✓ {row.schema_name}.{row.table_name}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Base de datos MercadoBursatil configurada correctamente\n")
        
    except pyodbc.Error as e:
        print(f"\n❌ Error de conexión o ejecución:")
        print(f"   {e}\n")
        return False
    
    return True

if __name__ == '__main__':
    ejecutar_script_sql()
