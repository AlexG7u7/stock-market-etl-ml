#!/usr/bin/env python3
"""
Test local del flujo completo de carga de tickers
Simula la API para no consumir tokens
"""

import os
import sys
from pathlib import Path

# Configurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("="*60)
print("TEST LOCAL - CARGA DE TICKERS")
print("="*60)

# 1. Verificar variables de entorno
print("\n1. VERIFICANDO VARIABLES DE ENTORNO")
print("-"*60)

from dotenv import load_dotenv

env_file = project_root / '.env'
print(f"Buscando .env en: {env_file}")

if env_file.exists():
    print("[OK] Archivo .env encontrado")
    load_dotenv(env_file)
else:
    print("[NO] Archivo .env NO encontrado")
    print("Creando .env de prueba...")
    
    # Crear .env de prueba
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write("\n")  # Salto de línea inicial
        f.write("# API DataBursátil\n")
        f.write("DATABURSATIL_API_TOKEN=test_token_local_1234567890\n")
        f.write("\n")
        f.write("# SQL Server\n")
        f.write("SQL_SERVER=localhost\n")
        f.write("SQL_DATABASE=MercadoBursatil\n")
        f.write("SQL_USER=rodrigo\n")
        f.write("SQL_PASSWORD=rodrigo\n")
        f.write("SQL_DRIVER=ODBC Driver 17 for SQL Server\n")
        f.write("\n")
        f.write("# Configuración\n")
        f.write("LOG_LEVEL=INFO\n")
    
    print("[OK] Archivo .env creado")
    load_dotenv(env_file)

# Verificar que se cargaron
api_token = os.getenv('DATABURSATIL_API_TOKEN')
sql_server = os.getenv('SQL_SERVER')
sql_database = os.getenv('SQL_DATABASE')
sql_user = os.getenv('SQL_USER')

print(f"API_TOKEN: {'[OK] ' + api_token[:20] + '...' if api_token else '[NO] NO CONFIGURADO'}")
print(f"SQL_SERVER: {'[OK] ' + sql_server if sql_server else '[NO] NO CONFIGURADO'}")
print(f"SQL_DATABASE: {'[OK] ' + sql_database if sql_database else '[NO] NO CONFIGURADO'}")
print(f"SQL_USER: {'[OK] ' + sql_user if sql_user else '[NO] NO CONFIGURADO'}")

# 2. Test de conexión a BD
print("\n2. PROBANDO CONEXION A BASE DE DATOS")
print("-"*60)

try:
    from src.db.connection import get_connection
    print("Conectando...")
    conn = get_connection()
    cursor = conn.cursor()
    
    # Query simple
    cursor.execute("SELECT @@VERSION")
    version = cursor.fetchone()[0]
    print(f"[OK] Conexión exitosa")
    print(f"SQL Server: {version[:60]}...")
    
    # Verificar que existen las tablas
    cursor.execute("""
        SELECT name FROM sys.tables 
        WHERE schema_id = SCHEMA_ID('stage')
        ORDER BY name
    """)
    tablas = [row[0] for row in cursor.fetchall()]
    print(f"[OK] Tablas en schema 'stage': {', '.join(tablas)}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"[ERROR] No se pudo conectar a la BD: {e}")
    print("Asegúrate de que SQL Server esté corriendo y las credenciales sean correctas")
    sys.exit(1)

# 3. Test de API (simulado)
print("\n3. SIMULANDO LLAMADA A API")
print("-"*60)

emisoras_simuladas = [
    {
        'symbol': 'ALFAA',
        'name': 'Alfa S.A.B. de C.V.',
        'sector': 'Industrial',
        'isin': 'MX01AL0A0004',
        'tipo_valor': 'Capital'
    },
    {
        'symbol': 'AMXL',
        'name': 'América Móvil',
        'sector': 'Telecomunicaciones',
        'isin': 'MX01AM0X1018',
        'tipo_valor': 'Capital'
    },
    {
        'symbol': 'GFNORTEO',
        'name': 'Grupo Financiero Banorte',
        'sector': 'Financiero',
        'isin': 'MX01GF000007',
        'tipo_valor': 'Capital'
    }
]

print(f"[OK] Simuladas {len(emisoras_simuladas)} emisoras")
for e in emisoras_simuladas:
    print(f"  - {e['symbol']:10s} | {e['name']}")

# 4. Test de inserción en BD
print("\n4. INSERTANDO DATOS DE PRUEBA EN BD")
print("-"*60)

try:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Registrar llamada a API
    cursor.execute("""
        INSERT INTO control.api_calls (endpoint, status_code, records_returned)
        VALUES (?, ?, ?)
    """, ('/v2/emisoras', 200, len(emisoras_simuladas)))
    print("[OK] Registrada llamada en control.api_calls")
    
    insertados = 0
    actualizados = 0
    
    for emisora in emisoras_simuladas:
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
    
    print(f"[OK] {insertados} tickers nuevos")
    print(f"[OK] {actualizados} tickers actualizados")
    
    # Registrar en log
    cursor.execute("""
        INSERT INTO control.etl_log 
        (etl_process, status, records_processed, mensaje)
        VALUES (?, ?, ?, ?)
    """, (
        'test_local',
        'SUCCESS',
        insertados + actualizados,
        f'{insertados} nuevos, {actualizados} actualizados'
    ))
    conn.commit()
    
    # Verificar resultados
    cursor.execute("SELECT COUNT(*) FROM stage.cat_tickers WHERE activo = 1")
    total = cursor.fetchone()[0]
    print(f"[OK] Total de tickers activos en BD: {total}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("TEST COMPLETADO EXITOSAMENTE")
    print("="*60)
    print("\nAhora puedes ejecutar el script real:")
    print("  python src/etl/cargar_tickers.py")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
