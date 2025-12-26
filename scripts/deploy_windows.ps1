# Script de deployment para Windows Server
# Ejecutar manualmente: .\scripts\deploy_windows.ps1

Write-Host "🚀 Iniciando deployment..." -ForegroundColor Green

# Ir al directorio del proyecto
Set-Location "C:\Projects\stock-market"

# Verificar estado de Git
Write-Host "`n📊 Estado actual:" -ForegroundColor Cyan
git status

# Hacer pull de los últimos cambios
Write-Host "`n📥 Descargando cambios desde GitHub..." -ForegroundColor Cyan
git pull origin main

# Verificar si hay cambios en SQL
$sqlChanged = git diff --name-only HEAD@{1} HEAD | Select-String "sql/"

if ($sqlChanged) {
    Write-Host "`n🗄️ Detectados cambios en SQL, ejecutando schema..." -ForegroundColor Yellow
    sqlcmd -S localhost -U rodrigo -P rodrigo -i "C:\Projects\stock-market\sql\01_create_schema.sql"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Schema SQL ejecutado correctamente" -ForegroundColor Green
    } else {
        Write-Host "❌ Error al ejecutar schema SQL" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`nℹ️  No hay cambios en SQL, saltando ejecución de schema" -ForegroundColor Gray
}

Write-Host "`n✅ Deployment completado!" -ForegroundColor Green
Write-Host "📦 Proyecto actualizado en: C:\Projects\stock-market" -ForegroundColor Cyan
