#!/usr/bin/env python3
"""
Script de diagnóstico para verificar variables de entorno
"""

import os
import sys
from pathlib import Path

print("="*60)
print("🔍 DIAGNÓSTICO DE VARIABLES DE ENTORNO")
print("="*60)

# Información del sistema
print(f"\n📍 Directorio actual: {os.getcwd()}")
print(f"📍 Script ubicado en: {Path(__file__).parent}")
print(f"🐍 Python: {sys.version}")
print(f"🐍 Ejecutable: {sys.executable}")

# Variables de entorno
print("\n" + "="*60)
print("🔑 VARIABLES DE ENTORNO")
print("="*60)

variables = [
    'DATABURSATIL_API_TOKEN',
    'SQL_SERVER',
    'SQL_DATABASE', 
    'SQL_USER',
    'SQL_PASSWORD',
    'SQL_DRIVER',
    'LOG_LEVEL'
]

for var in variables:
    valor = os.getenv(var)
    if valor:
        # Ocultar valores sensibles
        if 'TOKEN' in var or 'PASSWORD' in var:
            display = f"{valor[:10]}..." if len(valor) > 10 else "***"
        else:
            display = valor
        print(f"✅ {var:30s} = {display}")
    else:
        print(f"❌ {var:30s} = NO CONFIGURADO")

# Verificar archivo .env
print("\n" + "="*60)
print("📄 VERIFICACIÓN DE ARCHIVO .env")
print("="*60)

project_root = Path(__file__).parent
env_file = project_root / '.env'

print(f"📁 Ruta del proyecto: {project_root}")
print(f"📄 Buscando .env en: {env_file}")

if env_file.exists():
    print(f"✅ Archivo .env EXISTE")
    print(f"📏 Tamaño: {env_file.stat().st_size} bytes")
    print("\n📋 Contenido:")
    print("-"*60)
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Ocultar valores sensibles en el output
                if '=' in line:
                    key, value = line.split('=', 1)
                    if 'TOKEN' in key or 'PASSWORD' in key:
                        print(f"{key}={value[:10]}...")
                    else:
                        print(line)
    print("-"*60)
else:
    print(f"❌ Archivo .env NO EXISTE")

# Test de carga con python-dotenv
print("\n" + "="*60)
print("🧪 TEST DE CARGA CON python-dotenv")
print("="*60)

try:
    from dotenv import load_dotenv
    print("✅ Módulo dotenv importado correctamente")
    
    if env_file.exists():
        print(f"⏳ Cargando {env_file}...")
        result = load_dotenv(env_file)
        print(f"{'✅' if result else '❌'} load_dotenv() retornó: {result}")
        
        # Re-verificar variables después de cargar
        print("\n📋 Variables DESPUÉS de load_dotenv():")
        for var in variables:
            valor = os.getenv(var)
            if valor:
                if 'TOKEN' in var or 'PASSWORD' in var:
                    display = f"{valor[:10]}..."
                else:
                    display = valor
                print(f"✅ {var:30s} = {display}")
            else:
                print(f"❌ {var:30s} = NO CONFIGURADO")
    
except ImportError:
    print("❌ Módulo python-dotenv NO instalado")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*60)
print("✅ DIAGNÓSTICO COMPLETADO")
print("="*60)
