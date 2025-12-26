# Script para actualizar dependencias Python
# Ejecutar: .\scripts\update_deps.ps1

Write-Host "📚 Actualizando dependencias Python..." -ForegroundColor Green

# Ir al directorio del proyecto
Set-Location "C:\Projects\stock-market"

# Actualizar pip primero
Write-Host "`n⬆️  Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Instalar/actualizar todas las dependencias
Write-Host "`n📦 Instalando/actualizando paquetes desde requirements.txt..." -ForegroundColor Cyan
pip install -r requirements.txt --upgrade

# Mostrar lo que se instaló
Write-Host "`n✅ Dependencias actualizadas:" -ForegroundColor Green
pip list | Select-String -Pattern "pandas|numpy|requests|pyodbc|pymssql|sqlalchemy|python-dotenv|httpx|jsonschema"

Write-Host "`n🎉 ¡Actualización completada!" -ForegroundColor Green
