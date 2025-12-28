"""
Script para configurar Windows Scheduled Task para ETL incremental
Ejecuta diariamente WALMEX y ALSEA a las 4 PM
"""
import subprocess
import sys
import os
from pathlib import Path

def crear_task():
    """Crea la Scheduled Task en Windows"""
    
    TASK_NAME = "ETL-Incremental-StockMarket"
    HORA = "16:00"  # 4 PM
    PROJECT_PATH = r"C:\Projects\stock-market"
    
    # Script batch que ejecutará ambos tickers
    batch_script = f"""@echo off
cd /d {PROJECT_PATH}
echo ========================================
echo ETL INCREMENTAL - %DATE% %TIME%
echo ========================================

echo.
echo [1/2] Ejecutando WALMEX incremental...
python -m src.etl.walmex.incremental
if errorlevel 1 (
    echo ERROR: WALMEX incremental fallo
) else (
    echo OK: WALMEX incremental exitoso
)

echo.
echo [2/2] Ejecutando ALSEA incremental...
python -m src.etl.alsea.incremental
if errorlevel 1 (
    echo ERROR: ALSEA incremental fallo
) else (
    echo OK: ALSEA incremental exitoso
)

echo.
echo ========================================
echo ETL COMPLETADO - %DATE% %TIME%
echo ========================================
"""
    
    # Guardar el batch script
    batch_path = Path(PROJECT_PATH) / "scripts" / "ejecutar_etl_incremental.bat"
    batch_path.parent.mkdir(exist_ok=True)
    
    print(f"📝 Creando script batch: {batch_path}")
    with open(batch_path, 'w') as f:
        f.write(batch_script)
    print("✅ Script batch creado")
    
    # Eliminar tarea si ya existe
    print(f"\n🗑️  Eliminando tarea existente (si existe)...")
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True
    )
    
    # Crear nueva tarea
    print(f"\n⚙️  Creando Scheduled Task: {TASK_NAME}")
    print(f"   Hora: {HORA} (4 PM)")
    print(f"   Días: Lunes a Sábado")
    print(f"   Script: {batch_path}")
    
    # Comando para crear la tarea
    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", str(batch_path),
        "/SC", "WEEKLY",
        "/D", "MON,TUE,WED,THU,FRI,SAT",  # Lunes a Sábado
        "/ST", HORA,
        "/F"  # Force (sobrescribe si existe)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n✅ Scheduled Task creada exitosamente!")
        
        # Mostrar información de la tarea
        print("\n📋 Información de la tarea:")
        info = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True,
            text=True
        )
        
        # Extraer líneas importantes
        for line in info.stdout.split('\n'):
            if any(keyword in line for keyword in ['Task Name', 'Next Run Time', 'Schedule', 'Task To Run']):
                print(f"   {line.strip()}")
        
        # Preguntar si ejecutar ahora
        print("\n❓ ¿Deseas ejecutar la tarea ahora para probarla? (s/n): ", end='')
        respuesta = input().strip().lower()
        
        if respuesta == 's':
            print("\n🚀 Ejecutando tarea...")
            run_result = subprocess.run(
                ["schtasks", "/Run", "/TN", TASK_NAME],
                capture_output=True,
                text=True
            )
            
            if run_result.returncode == 0:
                print("✅ Tarea ejecutada. Revisa los logs arriba.")
            else:
                print(f"❌ Error al ejecutar: {run_result.stderr}")
        
        print("\n" + "="*50)
        print("✅ CONFIGURACIÓN COMPLETADA")
        print("="*50)
        print("\n💡 La tarea se ejecutará automáticamente:")
        print("   - Lunes a Sábado a las 4:00 PM")
        print("   - Carga datos del día anterior")
        print("   - WALMEX y ALSEA")
        print("\n📝 Para ver logs en tiempo real:")
        print(f"   schtasks /Run /TN {TASK_NAME}")
        print("\n🗑️  Para eliminar la tarea:")
        print(f"   schtasks /Delete /TN {TASK_NAME} /F")
        print()
        
        return 0
    else:
        print(f"\n❌ Error al crear la tarea:")
        print(result.stderr)
        return 1

if __name__ == "__main__":
    try:
        sys.exit(crear_task())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)
