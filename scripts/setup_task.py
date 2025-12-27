"""
Script para configurar Scheduled Task usando Python
Más confiable para ejecución remota via SSH
"""

import subprocess
import sys
import os
from pathlib import Path

# Colores ANSI para Windows
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.CYAN}{'='*50}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^50}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*50}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.YELLOW}📋 {text}{Colors.RESET}")

def print_step(step, total, text):
    print(f"{Colors.YELLOW}[{step}/{total}] {text}{Colors.RESET}")

def check_admin():
    """Verificar si se ejecuta como administrador"""
    try:
        # Intentar ejecutar comando que requiere admin
        result = subprocess.run(
            ["net", "session"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False

def task_exists(task_name):
    """Verificar si la tarea ya existe"""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name],
        capture_output=True
    )
    return result.returncode == 0

def delete_task(task_name):
    """Eliminar tarea existente"""
    subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True
    )

def create_task(task_name, python_script, hora="16:00", usuario="rodrigo"):
    """Crear scheduled task"""
    cmd = [
        "schtasks",
        "/Create",
        "/TN", task_name,
        "/TR", f'python "{python_script}"',
        "/SC", "DAILY",
        "/ST", hora,
        "/RU", usuario,
        "/IT",  # Interactive token (permite ejecutar sin login)
        "/F"    # Force (sobrescribe si existe)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

def query_task(task_name):
    """Obtener información de la tarea"""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
        capture_output=True,
        text=True
    )
    return result.stdout if result.returncode == 0 else None

def run_task(task_name):
    """Ejecutar tarea inmediatamente"""
    result = subprocess.run(
        ["schtasks", "/Run", "/TN", task_name],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def main():
    print_header("Configuración de Scheduled Task - ETL")
    
    # Configuración
    TASK_NAME = "ETL-Incremental-StockMarket"
    HORA = "16:00"
    USUARIO = "rodrigo"
    PROJECT_PATH = Path("C:/Projects/stock-market")
    PYTHON_SCRIPT = PROJECT_PATH / "src" / "etl" / "ejecutar_etl_incremental.py"
    
    # Paso 1: Verificar admin
    print_step(1, 5, "Verificando permisos de administrador...")
    if not check_admin():
        print_error("Se requieren permisos de administrador")
        print("\nEjecuta PowerShell como Administrador y corre:")
        print(f"{Colors.GRAY}  python {__file__}{Colors.RESET}\n")
        return 1
    print_success("Permisos confirmados\n")
    
    # Paso 2: Verificar archivos
    print_step(2, 5, "Verificando archivos del proyecto...")
    if not PYTHON_SCRIPT.exists():
        print_error(f"Script no encontrado: {PYTHON_SCRIPT}")
        print("\nAsegúrate de haber ejecutado:")
        print(f"{Colors.GRAY}  cd C:\\Projects\\stock-market{Colors.RESET}")
        print(f"{Colors.GRAY}  git pull{Colors.RESET}\n")
        return 1
    print_success(f"Script encontrado: {PYTHON_SCRIPT.name}\n")
    
    # Paso 3: Eliminar tarea existente
    print_step(3, 5, "Verificando tarea existente...")
    if task_exists(TASK_NAME):
        print(f"   {Colors.GRAY}Eliminando tarea anterior...{Colors.RESET}")
        delete_task(TASK_NAME)
        print_success("Tarea anterior eliminada\n")
    else:
        print(f"   {Colors.GRAY}No existe tarea anterior{Colors.RESET}\n")
    
    # Paso 4: Crear nueva tarea
    print_step(4, 5, "Creando nueva tarea...")
    print(f"   {Colors.GRAY}Nombre: {TASK_NAME}{Colors.RESET}")
    print(f"   {Colors.GRAY}Horario: Diario a las {HORA}{Colors.RESET}")
    print(f"   {Colors.GRAY}Usuario: {USUARIO}{Colors.RESET}")
    print()
    
    success, stdout, stderr = create_task(
        TASK_NAME, 
        str(PYTHON_SCRIPT), 
        HORA, 
        USUARIO
    )
    
    if not success:
        print_error("No se pudo crear la tarea")
        print(f"\n{Colors.RED}Error:{Colors.RESET}")
        print(stderr)
        return 1
    
    print_success("Tarea creada exitosamente\n")
    
    # Paso 5: Verificar configuración
    print_step(5, 5, "Verificando configuración...")
    task_info = query_task(TASK_NAME)
    
    if task_info:
        # Extraer información relevante
        for line in task_info.split('\n'):
            if any(key in line for key in ['Nombre de tarea:', 'Estado:', 'Siguiente hora de ejecución:', 'Última hora de ejecución:']):
                print(f"   {Colors.GRAY}{line.strip()}{Colors.RESET}")
    
    print_success("Configuración verificada\n")
    
    # Resumen
    print_header("✅ CONFIGURACIÓN COMPLETADA")
    
    print(f"{Colors.YELLOW}📋 Información de la tarea:{Colors.RESET}")
    print(f"   Nombre: {TASK_NAME}")
    print(f"   Frecuencia: Diario")
    print(f"   Horario: {HORA}")
    print(f"   Script: {PYTHON_SCRIPT.name}")
    print()
    
    print(f"{Colors.YELLOW}📚 Comandos útiles:{Colors.RESET}")
    print(f"   Ver estado:")
    print(f"   {Colors.GRAY}schtasks /Query /TN \"{TASK_NAME}\" /FO LIST{Colors.RESET}")
    print()
    print(f"   Ejecutar ahora:")
    print(f"   {Colors.GRAY}schtasks /Run /TN \"{TASK_NAME}\"{Colors.RESET}")
    print()
    print(f"   Eliminar:")
    print(f"   {Colors.GRAY}schtasks /Delete /TN \"{TASK_NAME}\" /F{Colors.RESET}")
    print()
    
    # Preguntar si quiere ejecutar ahora
    print(f"{Colors.YELLOW}🧪 ¿Ejecutar tarea AHORA para probar?{Colors.RESET}")
    respuesta = input("   (S/N): ").strip().upper()
    
    if respuesta == 'S' or respuesta == 'Y':
        print()
        print(f"{Colors.YELLOW}🚀 Ejecutando tarea...{Colors.RESET}")
        if run_task(TASK_NAME):
            print_success("Tarea iniciada")
            print()
            print(f"{Colors.CYAN}💡 Revisa los logs en:{Colors.RESET}")
            print(f"   {Colors.GRAY}C:\\Projects\\stock-market\\logs\\{Colors.RESET}")
        else:
            print_error("No se pudo ejecutar la tarea")
    else:
        print()
        print_success(f"Tarea configurada. Se ejecutará automáticamente a las {HORA}")
    
    print()
    print(f"{Colors.CYAN}{'='*50}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'🎉 ¡LISTO!':^50}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*50}{Colors.RESET}\n")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Cancelado por el usuario{Colors.RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error inesperado:{Colors.RESET}")
        print(f"{Colors.RED}{e}{Colors.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
