# Script para configurar Scheduled Task en Windows Server
# Ejecuta el ETL incremental todos los días a las 4 PM hora local

param(
    [string]$Hora = "16:00",  # 4 PM por defecto
    [string]$Usuario = "rodrigo",
    [string]$ProyectoPath = "C:\Projects\stock-market"
)

# Configurar colores y output
$Host.UI.RawUI.ForegroundColor = "White"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Configuración de Scheduled Task - ETL" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que estamos en Windows
Write-Host "[1/6] Verificando sistema operativo..." -ForegroundColor Yellow
if ($PSVersionTable.Platform -eq "Unix") {
    Write-Host "❌ Este script solo funciona en Windows Server" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Windows detectado" -ForegroundColor Green
Write-Host ""

# Verificar permisos de administrador
Write-Host "[2/6] Verificando permisos de administrador..." -ForegroundColor Yellow
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $esAdmin) {
    Write-Host "❌ Se requieren permisos de administrador" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor:" -ForegroundColor Yellow
    Write-Host "1. Click derecho en el menú de Windows" -ForegroundColor White
    Write-Host "2. Seleccionar 'Windows PowerShell (Admin)'" -ForegroundColor White
    Write-Host "3. Volver a ejecutar este script" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}
Write-Host "✅ Permisos de administrador confirmados" -ForegroundColor Green
Write-Host ""
Write-Host "✅ Permisos de administrador confirmados" -ForegroundColor Green
Write-Host ""

# Configuración de la tarea
Write-Host "[3/6] Verificando archivos del proyecto..." -ForegroundColor Yellow
$TaskName = "ETL-Incremental-StockMarket"
$TaskDescription = "Carga incremental diaria de precios de acciones desde Yahoo Finance"

# Script Python a ejecutar
$PythonScript = Join-Path $ProyectoPath "src\etl\ejecutar_etl_incremental.py"

Write-Host "   Proyecto: $ProyectoPath" -ForegroundColor Gray
Write-Host "   Script: $PythonScript" -ForegroundColor Gray

if (-not (Test-Path $ProyectoPath)) {
    Write-Host "❌ Directorio del proyecto no encontrado: $ProyectoPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $PythonScript)) {
    Write-Host "❌ Script de ETL no encontrado: $PythonScript" -ForegroundColor Red
    Write-Host ""
    Write-Host "Asegúrate de haber ejecutado:" -ForegroundColor Yellow
    Write-Host "   cd C:\Projects\stock-market" -ForegroundColor White
    Write-Host "   git pull" -ForegroundColor White
    exit 1
}
Write-Host "✅ Archivos del proyecto encontrados" -ForegroundColor Green
Write-Host ""

# Verificar Python
Write-Host "[4/6] Verificando Python..." -ForegroundColor Yellow
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Host "❌ Python no encontrado en PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor instala Python o agrégalo al PATH del sistema" -ForegroundColor Yellow
    exit 1
}

$pythonVersion = & python --version
Write-Host "   Python encontrado: $pythonVersion" -ForegroundColor Gray
Write-Host "   Ubicación: $PythonExe" -ForegroundColor Gray
Write-Host "✅ Python configurado correctamente" -ForegroundColor Green
Write-Host ""

Write-Host "[5/6] Configurando Scheduled Task..." -ForegroundColor Yellow
Write-Host "   Nombre: $TaskName" -ForegroundColor Gray
Write-Host "   Horario: Todos los días a las $Hora" -ForegroundColor Gray
Write-Host "   Usuario: $Usuario" -ForegroundColor Gray
Write-Host ""

# Eliminar tarea existente si existe
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "   Eliminando tarea existente..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "   ✓ Tarea anterior eliminada" -ForegroundColor Gray
}

Write-Host "   Creando nueva tarea..." -ForegroundColor Yellow

# Crear acción (ejecutar Python script)
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$PythonScript`"" `
    -WorkingDirectory $ProyectoPath

Write-Host "   ✓ Acción configurada" -ForegroundColor Gray

# Crear trigger (todos los días a la hora especificada)
$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $Hora

Write-Host "   ✓ Trigger configurado (diario a las $Hora)" -ForegroundColor Gray

# Configuración adicional de la tarea
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Write-Host "   ✓ Configuración avanzada aplicada" -ForegroundColor Gray

# Crear principal (usuario que ejecuta la tarea)
$Principal = New-ScheduledTaskPrincipal `
    -UserId $Usuario `
    -LogonType S4U `
    -RunLevel Limited

Write-Host "   ✓ Usuario configurado: $Usuario" -ForegroundColor Gray

# Registrar la tarea
Write-Host "   Registrando tarea en el sistema..." -ForegroundColor Yellow
Write-Host "   Registrando tarea en el sistema..." -ForegroundColor Yellow

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Description $TaskDescription `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Force | Out-Null
    
    Write-Host "✅ Scheduled Task creado exitosamente!" -ForegroundColor Green
    Write-Host ""
    
    # Mostrar información de la tarea
    Write-Host "[6/6] Verificando configuración..." -ForegroundColor Yellow
    $task = Get-ScheduledTask -TaskName $TaskName
    $taskInfo = $task | Get-ScheduledTaskInfo
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  ✅ CONFIGURACIÓN COMPLETADA" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "📋 Información de la Tarea:" -ForegroundColor Yellow
    Write-Host "   Nombre: $($task.TaskName)" -ForegroundColor White
    Write-Host "   Estado: $($task.State)" -ForegroundColor White
    Write-Host "   Descripción: $TaskDescription" -ForegroundColor Gray
    Write-Host ""
    Write-Host "⏰ Programación:" -ForegroundColor Yellow
    Write-Host "   Frecuencia: Diario" -ForegroundColor White
    Write-Host "   Horario: $Hora" -ForegroundColor White
    Write-Host "   Próxima ejecución: $($taskInfo.NextRunTime)" -ForegroundColor Green
    
    if ($taskInfo.LastRunTime) {
        Write-Host "   Última ejecución: $($taskInfo.LastRunTime)" -ForegroundColor White
        
        $lastResult = $taskInfo.LastTaskResult
        if ($lastResult -eq 0) {
            Write-Host "   Último resultado: ✅ Éxito (código 0)" -ForegroundColor Green
        } else {
            Write-Host "   Último resultado: ⚠️ Código $lastResult" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "📂 Configuración:" -ForegroundColor Yellow
    Write-Host "   Directorio: $ProyectoPath" -ForegroundColor White
    Write-Host "   Script: ejecutar_etl_incremental.py" -ForegroundColor White
    Write-Host "   Usuario: $Usuario" -ForegroundColor White
    Write-Host ""
    
    Write-Host ""
    
    # Opciones para el usuario
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  📚 COMANDOS ÚTILES" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Ver estado:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Format-List" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ejecutar manualmente ahora:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Ver logs de Python:" -ForegroundColor Yellow
    Write-Host "  Get-Content C:\Projects\stock-market\logs\*.log -Tail 50" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Eliminar la tarea:" -ForegroundColor Yellow
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Preguntar si quiere ejecutar ahora para probar
    Write-Host "🧪 ¿Deseas ejecutar la tarea AHORA para probarla? (S/N): " -ForegroundColor Yellow -NoNewline
    $respuesta = Read-Host
    
    if ($respuesta -eq "S" -or $respuesta -eq "s" -or $respuesta -eq "Y" -or $respuesta -eq "y") {
        Write-Host ""
        Write-Host "🚀 Ejecutando tarea de prueba..." -ForegroundColor Yellow
        Write-Host ""
        
        Start-ScheduledTask -TaskName $TaskName
        
        Write-Host "✅ Tarea iniciada!" -ForegroundColor Green
        Write-Host ""
        Write-Host "⏳ Esperando 3 segundos..." -ForegroundColor Yellow
        Start-Sleep -Seconds 3
        
        Write-Host ""
        Write-Host "📊 Estado actual:" -ForegroundColor Yellow
        $currentTask = Get-ScheduledTask -TaskName $TaskName
        Write-Host "   Estado: $($currentTask.State)" -ForegroundColor White
        
        Write-Host ""
        Write-Host "💡 Revisa los logs en:" -ForegroundColor Cyan
        Write-Host "   Task Scheduler → $TaskName → History" -ForegroundColor White
        Write-Host ""
        Write-Host "   O ejecuta:" -ForegroundColor White
        Write-Host "   Get-Content C:\Projects\stock-market\logs\*.log -Tail 50 -Wait" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host ""
        Write-Host "👍 Tarea configurada. Se ejecutará automáticamente a las $Hora" -ForegroundColor Green
        Write-Host ""
    }
    
} catch {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  ❌ ERROR" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error al crear Scheduled Task:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Stack trace:" -ForegroundColor Gray
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    Write-Host ""
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  🎉 ¡LISTO!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "El ETL se ejecutará automáticamente todos los días a las $Hora" -ForegroundColor White
Write-Host ""
