# Script de setup del entorno para Windows
# Ejecutar: .\scripts\setup_env.ps1

Write-Host "🚀 Iniciando setup del entorno..." -ForegroundColor Green

# Verificar Python
Write-Host "`n📦 Verificando Python..." -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python no está instalado" -ForegroundColor Red
    exit 1
}

# Ir al directorio del proyecto
Set-Location "C:\Projects\stock-market"

# Actualizar pip
Write-Host "`n⬆️  Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Instalar/actualizar dependencias
Write-Host "`n📚 Instalando dependencias desde requirements.txt..." -ForegroundColor Cyan
pip install -r requirements.txt --upgrade

# Verificar archivo .env
Write-Host "`n🔐 Verificando archivo .env..." -ForegroundColor Cyan
if (!(Test-Path ".env")) {
    Write-Host "⚠️  Archivo .env no encontrado, creando desde plantilla..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "📝 IMPORTANTE: Edita .env y configura tus credenciales" -ForegroundColor Yellow
    notepad .env
} else {
    Write-Host "✅ Archivo .env existe" -ForegroundColor Green
}

# Verificar conexión a SQL Server
Write-Host "`n🗄️  Verificando conexión a SQL Server..." -ForegroundColor Cyan
$testQuery = "SELECT @@VERSION"
$result = sqlcmd -S localhost -U rodrigo -P rodrigo -Q $testQuery -h -1 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Conexión a SQL Server exitosa" -ForegroundColor Green
} else {
    Write-Host "❌ Error al conectar a SQL Server" -ForegroundColor Red
    Write-Host "   Verifica que SQL Server esté corriendo" -ForegroundColor Yellow
}

# Verificar base de datos
Write-Host "`n📊 Verificando base de datos MercadoBursatil..." -ForegroundColor Cyan
$dbCheck = sqlcmd -S localhost -U rodrigo -P rodrigo -Q "SELECT name FROM sys.databases WHERE name = 'MercadoBursatil'" -h -1 2>&1
if ($dbCheck -match "MercadoBursatil") {
    Write-Host "✅ Base de datos MercadoBursatil existe" -ForegroundColor Green
} else {
    Write-Host "⚠️  Base de datos MercadoBursatil no encontrada" -ForegroundColor Yellow
    Write-Host "   Ejecuta: sqlcmd -S localhost -U rodrigo -P rodrigo -i sql\01_create_schema.sql" -ForegroundColor Yellow
}

# Listar paquetes instalados
Write-Host "`n📦 Paquetes Python instalados:" -ForegroundColor Cyan
pip list | Select-String -Pattern "pandas|numpy|requests|pyodbc|sqlalchemy|python-dotenv"

# Resumen
Write-Host "`n" + ("="*60) -ForegroundColor Green
Write-Host "✅ Setup completado!" -ForegroundColor Green
Write-Host ("="*60) -ForegroundColor Green
Write-Host "`n📋 Próximos pasos:" -ForegroundColor Cyan
Write-Host "   1. Verifica tu archivo .env con las credenciales correctas" -ForegroundColor White
Write-Host "   2. Prueba la carga de tickers: python src\etl\cargar_tickers.py" -ForegroundColor White
Write-Host "   3. Prueba la carga de precios: python src\etl\cargar_precios.py --ticker ALFAA --fecha-inicio 2024-01-01 --fecha-fin 2024-12-31" -ForegroundColor White
Write-Host "`n"
