@echo off
REM Script para configurar Scheduled Task usando SCHTASKS
REM Ejecutar como Administrador

echo ============================================
echo   Configuracion de Scheduled Task - ETL
echo ============================================
echo.

REM Verificar permisos de administrador
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [X] ERROR: Se requieren permisos de administrador
    echo.
    echo Ejecuta este script como Administrador:
    echo 1. Click derecho en el archivo
    echo 2. "Ejecutar como administrador"
    echo.
    pause
    exit /b 1
)

echo [OK] Permisos de administrador confirmados
echo.

REM Configuracion
set TASK_NAME=ETL-Incremental-StockMarket
set HORA=16:00
set PROYECTO_PATH=C:\Projects\stock-market
set PYTHON_SCRIPT=%PROYECTO_PATH%\src\etl\ejecutar_etl_incremental.py

echo Configuracion:
echo   Nombre: %TASK_NAME%
echo   Horario: Todos los dias a las %HORA%
echo   Script: %PYTHON_SCRIPT%
echo.

REM Verificar que existe el script
if not exist "%PYTHON_SCRIPT%" (
    echo [X] ERROR: Script no encontrado: %PYTHON_SCRIPT%
    echo.
    echo Asegurate de haber ejecutado:
    echo   cd C:\Projects\stock-market
    echo   git pull
    echo.
    pause
    exit /b 1
)

echo [OK] Script encontrado
echo.

REM Eliminar tarea existente si existe
echo Verificando si existe tarea anterior...
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorLevel% EQU 0 (
    echo Eliminando tarea existente...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul
    echo [OK] Tarea anterior eliminada
)
echo.

REM Crear nueva tarea
echo Creando nueva tarea programada...
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "python \"%PYTHON_SCRIPT%\"" ^
    /SC DAILY ^
    /ST %HORA% ^
    /RU rodrigo ^
    /IT ^
    /F

if %errorLevel% NEQ 0 (
    echo [X] ERROR: No se pudo crear la tarea
    pause
    exit /b 1
)

echo.
echo ============================================
echo   [OK] TAREA CREADA EXITOSAMENTE
echo ============================================
echo.

REM Mostrar informacion de la tarea
echo Informacion de la tarea:
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V
echo.

echo ============================================
echo   Comandos utiles
echo ============================================
echo.
echo Ejecutar ahora:
echo   schtasks /Run /TN "%TASK_NAME%"
echo.
echo Ver estado:
echo   schtasks /Query /TN "%TASK_NAME%" /FO LIST
echo.
echo Ver logs:
echo   type C:\Projects\stock-market\logs\*.log
echo.
echo Eliminar tarea:
echo   schtasks /Delete /TN "%TASK_NAME%" /F
echo.

echo.
set /p EJECUTAR="Deseas ejecutar la tarea AHORA para probarla? (S/N): "
if /i "%EJECUTAR%"=="S" (
    echo.
    echo Ejecutando tarea...
    schtasks /Run /TN "%TASK_NAME%"
    echo [OK] Tarea iniciada
    echo.
    echo Espera unos segundos y revisa los logs en:
    echo   C:\Projects\stock-market\logs\
)

echo.
echo ============================================
echo   [OK] CONFIGURACION COMPLETADA
echo ============================================
echo.
echo La tarea se ejecutara automaticamente
echo todos los dias a las %HORA%
echo.
pause
