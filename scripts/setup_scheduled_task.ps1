# Script para configurar Scheduled Task en Windows Server
# Ejecuta el ETL incremental todos los días a las 4 PM hora local

param(
    [string]$Hora = "16:00",  # 4 PM por defecto
    [string]$Usuario = "rodrigo",
    [string]$ProyectoPath = "C:\Projects\stock-market"
)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Configuración de Scheduled Task - ETL" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que estamos en Windows
if ($PSVersionTable.Platform -eq "Unix") {
    Write-Error "Este script solo funciona en Windows Server"
    exit 1
}

# Verificar permisos de administrador
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $esAdmin) {
    Write-Warning "⚠️  Se requieren permisos de administrador para crear Scheduled Tasks"
    Write-Host "Ejecuta PowerShell como Administrador y vuelve a correr este script"
    exit 1
}

# Configuración de la tarea
$TaskName = "ETL-Incremental-StockMarket"
$TaskDescription = "Carga incremental diaria de precios de acciones desde Yahoo Finance"

# Script Python a ejecutar
$PythonScript = Join-Path $ProyectoPath "src\etl\ejecutar_etl_incremental.py"
$PythonExe = (Get-Command python).Source

if (-not $PythonExe) {
    Write-Error "❌ Python no encontrado en PATH"
    exit 1
}

if (-not (Test-Path $PythonScript)) {
    Write-Error "❌ Script no encontrado: $PythonScript"
    exit 1
}

Write-Host "📝 Configuración:" -ForegroundColor Yellow
Write-Host "   Nombre: $TaskName"
Write-Host "   Horario: Todos los días a las $Hora"
Write-Host "   Script: $PythonScript"
Write-Host "   Python: $PythonExe"
Write-Host ""

# Eliminar tarea existente si existe
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "🗑️  Eliminando tarea existente..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Crear acción (ejecutar Python script)
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$PythonScript`"" `
    -WorkingDirectory $ProyectoPath

# Crear trigger (todos los días a la hora especificada)
$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $Hora

# Configuración adicional de la tarea
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Crear principal (usuario que ejecuta la tarea)
$Principal = New-ScheduledTaskPrincipal `
    -UserId $Usuario `
    -LogonType S4U `
    -RunLevel Limited

# Registrar la tarea
Write-Host "🔧 Registrando Scheduled Task..." -ForegroundColor Yellow

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
    $task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  Información de la Tarea" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "Nombre: $($task.TaskName)"
    Write-Host "Estado: $($task.State)"
    Write-Host "Próxima ejecución: $((Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo).NextRunTime)"
    Write-Host "Última ejecución: $((Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo).LastRunTime)"
    Write-Host ""
    
    # Opciones para el usuario
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  Comandos Útiles" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Ver estado de la tarea:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Format-List" -ForegroundColor White
    Write-Host ""
    Write-Host "Ejecutar manualmente ahora:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "Ver historial de ejecuciones:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor White
    Write-Host ""
    Write-Host "Ver logs en Event Viewer:" -ForegroundColor Yellow
    Write-Host "  eventvwr.msc → Task Scheduler → History" -ForegroundColor White
    Write-Host ""
    Write-Host "Eliminar la tarea:" -ForegroundColor Yellow
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor White
    Write-Host ""
    
    # Preguntar si quiere ejecutar ahora para probar
    $respuesta = Read-Host "¿Deseas ejecutar la tarea ahora para probarla? (S/N)"
    if ($respuesta -eq "S" -or $respuesta -eq "s") {
        Write-Host ""
        Write-Host "🚀 Ejecutando tarea..." -ForegroundColor Yellow
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        
        Write-Host "✅ Tarea iniciada. Revisa los logs en:" -ForegroundColor Green
        Write-Host "   Task Scheduler → Task Scheduler Library → $TaskName" -ForegroundColor White
        Write-Host ""
        Write-Host "También puedes revisar los logs de Python en la consola de salida" -ForegroundColor Cyan
    }
    
} catch {
    Write-Error "❌ Error al crear Scheduled Task: $_"
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "✅ Configuración completada" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
