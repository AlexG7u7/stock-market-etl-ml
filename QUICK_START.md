# 🚀 GUÍA DE INICIO RÁPIDO

## ✅ Lo que ya está hecho

1. **Estructura del proyecto completa** ✅
   - Carpetas organizadas (notebooks/, src/, config/, sql/, etc.)
   - Módulos Python base creados
   - Scripts SQL para base de datos

2. **Arquitectura de Base de Datos** ✅
   - Esquema completo para SQL Server
   - 7 tablas principales: emisoras, precios_historicos, features_ml, etc.
   - Índices optimizados para series temporales
   - 9 Stored Procedures útiles

3. **Módulos de Configuración** ✅
   - `src/utils/config.py` - Configuración centralizada
   - `src/utils/logger.py` - Sistema de logs
   - `src/db/connection.py` - Conexión SQL Server (pyodbc + SQLAlchemy)

## 📋 Próximos Pasos

### 1. Instalar Dependencias

```bash
cd ~/Projects/stock-market

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar cloudflared (si no lo tienes)
brew install cloudflare/cloudflare/cloudflared
```

### 2. Configurar Credenciales

```bash
# Copiar template de configuración
cp config/.env.example config/.env

# Editar con tus credenciales
nano config/.env
```

**Variables críticas a configurar:**
```env
DATABURSATIL_API_TOKEN=tu_token_de_30_caracteres
SQL_SERVER_PASSWORD=tu_password_sql_server
```

### 3. Probar Conexión SSH

```bash
# Conectar a tu laptop Windows vía Cloudflare
cloudflared access ssh --hostname ssh.rod-b-op.com --user rodri
```

En Windows, asegúrate que SQL Server:
- Esté corriendo
- Tenga autenticación SQL habilitada
- Puerto 1433 abierto en firewall local

### 4. Inicializar Base de Datos

```bash
# Ejecutar script de setup
python scripts/setup_database.py
```

Este script:
- Creará la base de datos `MercadoBursatil`
- Creará todas las tablas
- Creará índices optimizados
- Creará stored procedures

### 5. Probar Conexión

```bash
# Test de conexión básico
python src/db/connection.py
```

## 📊 Esquema de Base de Datos

### Tablas Principales

1. **`emisoras`** - Catálogo de emisoras y series
   - ticker, serie, emisora_serie (PK)
   - razon_social, mercado (local/global), bolsa (BMV/BIVA)

2. **`precios_historicos`** - Precios OHLCV diarios
   - emisora_serie, fecha, close, open, high, low, volume
   - importe, operaciones, PPP, cambios
   - Índice único: (emisora_serie, fecha, bolsa)

3. **`features_ml`** - Features extensibles para ML
   - emisora_serie, fecha, feature_name, feature_value
   - Diseño flexible para agregar cualquier feature nueva

4. **`etl_log`** - Control de ejecuciones ETL
   - Rastrea cada ejecución con estadísticas
   - Monitorea créditos consumidos

### Stored Procedures Útiles

```sql
-- Obtener último precio
EXEC sp_ultimo_precio @emisora_serie = 'WALMEX*'

-- Ver rango de fechas disponibles
EXEC sp_rango_fechas_disponibles

-- Detectar gaps en datos
EXEC sp_detectar_gaps @emisora_serie = 'WALMEX*', @dias_gap = 7

-- Estadísticas de ETL
EXEC sp_estadisticas_etl @dias_atras = 30

-- Resumen de emisora
EXEC sp_resumen_emisora @emisora_serie = 'WALMEX*'
```

## 🔄 Flujo de Trabajo ETL

### ETL Histórico (Carga Inicial)

```python
# En notebook: 01_etl_historico.ipynb
from src.api.databursatil import DataBursatilAPI
from src.db.connection import SQLServerConnection
from src.etl.orchestrator import ETLOrchestrator

# Configurar
tickers = ['WALMEX*', 'AMXB', 'CEMEXCPO']
start_date = '2020-01-01'
end_date = '2024-12-31'

# Ejecutar ETL
etl = ETLOrchestrator(mode='historico')
etl.run(tickers=tickers, start_date=start_date, end_date=end_date)
```

### ETL Cotidiano (Actualización Diaria)

```python
# En notebook: 02_etl_cotidiano.ipynb
from src.etl.orchestrator import ETLOrchestrator

# Detecta automáticamente qué fechas faltan
etl = ETLOrchestrator(mode='cotidiano')
etl.run()  # Solo trae datos nuevos desde última ejecución
```

## 🎯 Estructura de Datos para ML

### Datos OHLCV Base
```python
import pandas as pd
from src.db.connection import get_connection

with get_connection(use_sqlalchemy=True) as engine:
    query = """
        SELECT 
            fecha, emisora_serie,
            open, high, low, close, volume,
            cambio_porcentual
        FROM precios_historicos
        WHERE emisora_serie = 'WALMEX*'
        AND fecha >= '2023-01-01'
        ORDER BY fecha
    """
    df = pd.read_sql(query, engine)
```

### Features Extensibles
```python
# Calcular feature (ej: SMA_20)
# Guardar en tabla features_ml
insert_query = """
    INSERT INTO features_ml 
    (emisora_serie, fecha, feature_name, feature_value, feature_type)
    VALUES (?, ?, ?, ?, ?)
"""
```

**Ventajas del diseño:**
- ✅ Agregar nuevas features sin modificar esquema
- ✅ Cada feature tiene su propia fila
- ✅ Metadata JSON para features complejas
- ✅ Fácil filtrar por tipo de feature

## 🔍 Validación de Datos

```python
# Detectar gaps automáticamente
from src.db.connection import SQLServerConnection

conn = SQLServerConnection()
gaps = conn.execute_stored_procedure(
    'sp_detectar_gaps', 
    ('WALMEX*', 7)  # emisora, días_gap
)
```

## 📈 Próximos Módulos a Crear

1. **API Wrapper** (`src/api/databursatil.py`)
   - Consumir endpoints /v2/historicos, /v2/cotizaciones, /v2/emisoras
   - Manejo de rate limits y reintentos
   - Logging de créditos consumidos

2. **ETL Modules** (`src/etl/`)
   - `extractor.py` - Descarga datos de API
   - `transformer.py` - Limpieza y transformación
   - `loader.py` - Carga a SQL Server
   - `orchestrator.py` - Orquestación completa

3. **Notebooks**
   - `01_etl_historico.ipynb` - Carga inicial
   - `02_etl_cotidiano.ipynb` - Actualización diaria
   - `03_exploracion_datos.ipynb` - EDA
   - `04_gestion_tickers.ipynb` - Catálogo emisoras

## 💡 Consejos

### Performance SQL Server
- Los índices ya están optimizados para queries temporales
- Usa índices COLUMNSTORE si tienes SQL Server Enterprise/Standard
- Considera particionamiento por fecha si manejas millones de registros

### API DataBursatil
- Tienes 200,000 créditos mensuales
- Cada KiB descargado = 1 crédito
- Optimiza queries para minimizar consumo
- Usa endpoint `/v2/historicos` para carga masiva

### SSH Tunnel
- Cloudflare Access maneja el túnel automáticamente
- No necesitas configurar port forwarding manual
- La conexión se establece on-demand

## 🐛 Troubleshooting

### Error: "No se puede conectar a SQL Server"
1. Verifica que SQL Server esté corriendo en Windows
2. Confirma que autenticación SQL esté habilitada
3. Revisa firewall en Windows (puerto 1433)
4. Prueba conexión SSH: `cloudflared access ssh --hostname ssh.rod-b-op.com --user rodri`

### Error: "ODBC Driver not found"
```bash
# macOS
brew install unixodbc
brew tap microsoft/mssql-release
brew install msodbcsql17

# Verificar drivers instalados
odbcinst -q -d
```

### Error: "Módulo no encontrado"
```bash
# Asegúrate de estar en el directorio correcto
cd ~/Projects/stock-market

# Y que el venv esté activado
source venv/bin/activate

# Reinstalar dependencias si es necesario
pip install -r requirements.txt
```

## 📚 Documentación

- **API DataBursatil**: Ya tienes toda la documentación
- **SQL Server**: https://learn.microsoft.com/en-us/sql/
- **Cloudflare Tunnel**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/

## 🎉 ¡Estás listo!

Una vez completados los pasos 1-5, puedes empezar a crear los notebooks y módulos ETL.

**Siguiente archivo a crear**: `src/api/databursatil.py` (wrapper de la API)
