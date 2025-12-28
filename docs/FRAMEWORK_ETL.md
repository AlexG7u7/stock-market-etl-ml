# Framework ETL - Yahoo Finance para BMV

## 📋 Descripción

Framework modular y escalable para extracción, transformación y carga (ETL) de datos de la Bolsa Mexicana de Valores (BMV) usando Yahoo Finance como fuente principal.

## 🏗️ Arquitectura

```
src/etl/
├── shared/              # Componentes compartidos (framework)
│   ├── extractors/      # Extractores de datos
│   │   └── yahoo_finance.py    # YahooFinanceExtractor
│   ├── loaders/         # Cargadores a destinos
│   │   └── sql_server.py       # SQLServerLoader
│   └── models/          # Modelos de datos
│       └── precio.py            # PrecioHistorico
│
├── walmex/             # ETL específico para WALMEX
│   ├── incremental.py  # Carga diaria
│   └── historical.py   # Carga histórica (backfill)
│
├── alsea/              # ETL específico para ALSEA
│   ├── incremental.py
│   └── historical.py
│
└── [nuevo_ticker]/     # Agregar más tickers fácilmente
    ├── incremental.py
    └── historical.py
```

## ✨ Características

### ✅ Ventajas del Framework

1. **Modular y Reutilizable**
   - Componentes shared usados por todos los tickers
   - Agregar nuevos tickers en minutos

2. **Yahoo Finance como Fuente Principal**
   - ✅ GRATIS (sin costo ni API key)
   - ✅ OHLCV completo (Open, High, Low, Close, Volume)
   - ✅ Datos históricos confiables desde ~2000
   - ✅ Sin límite de requests (uso razonable)

3. **UPSERT Automático**
   - UPDATE si el registro existe
   - INSERT si es nuevo
   - Sin duplicados (constraint en BD)

4. **Logging Completo**
   - Logs coloridos con `loguru`
   - Trazabilidad de cada operación

5. **Type-Safe**
   - Modelos de datos con `dataclass`
   - Validaciones automáticas

## 🚀 Uso

### Instalación

```bash
# Activar entorno virtual
source venv/bin/activate

# Instalar dependencias
pip install yfinance loguru pyodbc python-dotenv
```

### Configurar Variables de Entorno

Crear `.env` con:

```bash
SQL_SERVER=localhost
SQL_DATABASE=MercadoBursatil
SQL_USER=tu_usuario
SQL_PASSWORD=tu_contraseña
```

### Ejecutar ETL Incremental (Diario)

```bash
# WALMEX - Último día disponible
python -m src.etl.walmex.incremental

# ALSEA - Último día disponible
python -m src.etl.alsea.incremental
```

### Ejecutar ETL Histórico (Backfill)

```bash
# WALMEX - 1 año (2024-12-27 a hoy)
python -m src.etl.walmex.historical --fecha-inicio 2024-12-27

# WALMEX - Rango específico
python -m src.etl.walmex.historical \
  --fecha-inicio 2024-01-01 \
  --fecha-fin 2024-12-31

# ALSEA - 1 año
python -m src.etl.alsea.historical --fecha-inicio 2024-12-27
```

## 🆕 Agregar Nuevo Ticker

### Opción 1: Usar el Generador (Recomendado)

```bash
# Generar estructura completa automáticamente
python crear_ticker_etl.py gfnorte "GFNORTEO"

# Output:
# ✅ Creando ETL para GFNORTE
#    Símbolo: GFNORTEO
#    Directorio: src/etl/gfnorte/
#    ✅ __init__.py
#    ✅ incremental.py
#    ✅ historical.py
```

### Opción 2: Manual

1. Copiar carpeta `walmex/` a `nuevo_ticker/`
2. Reemplazar `WALMEX*` por el nuevo símbolo
3. Actualizar comentarios

## 📊 Componentes del Framework

### 1. YahooFinanceExtractor

Extractor genérico para cualquier ticker de la BMV.

```python
from src.etl.shared.extractors import YahooFinanceExtractor

# Crear extractor
extractor = YahooFinanceExtractor(
    ticker_symbol="WALMEX*",
    ticker_id=12345  # ID de la BD
)

# Extraer último día
precios = extractor.extract_incremental(lookback_days=1)

# Extraer 1 año
precios = extractor.extract_historical(
    fecha_inicio=date(2024, 1, 1),
    fecha_fin=date(2024, 12, 31)
)

# Extraer último disponible
ultimo = extractor.extract_latest()
```

### 2. SQLServerLoader

Cargador con lógica UPSERT automática.

```python
from src.etl.shared.loaders import SQLServerLoader

# Crear loader
loader = SQLServerLoader(
    server="localhost",
    database="MercadoBursatil",
    username="user",
    password="pass"
)

# Cargar datos
stats = loader.load(precios)

# Output:
# {
#   'inserted': 200,
#   'updated': 50,
#   'errors': 0
# }

# Usar como context manager
with SQLServerLoader(...) as loader:
    stats = loader.load(precios)
```

### 3. PrecioHistorico

Modelo de datos que mapea a `stage.precios_historicos`.

```python
from src.etl.shared.models import PrecioHistorico
from datetime import date
from decimal import Decimal

precio = PrecioHistorico(
    ticker_id=12345,
    fecha=date(2025, 12, 26),
    open=Decimal('57.00'),
    high=Decimal('58.00'),
    low=Decimal('56.50'),
    close=Decimal('57.50'),
    volume=1000000
)

# Validaciones automáticas
# - close es obligatorio
# - Conversión automática a Decimal
```

## 🔄 Flujo de Datos

```
┌─────────────────┐
│ Yahoo Finance   │
│   (WALMEX.MX)   │
└────────┬────────┘
         │
         │ 1. EXTRACT
         ▼
┌─────────────────────┐
│ YahooFinanceExtractor│
│  - get OHLCV data   │
│  - parse dates      │
│  - create objects   │
└────────┬────────────┘
         │
         │ List[PrecioHistorico]
         ▼
┌─────────────────────┐
│  SQLServerLoader    │
│  - check if exists  │
│  - UPDATE or INSERT │
│  - commit batch     │
└────────┬────────────┘
         │
         │ 2. LOAD
         ▼
┌─────────────────────┐
│  SQL Server         │
│ stage.precios_hist  │
└─────────────────────┘
```

## 📅 Programación Diaria (Pendiente)

El ETL incremental se ejecutará automáticamente:

- **Hora**: 4:00 PM hora CDMX
- **Frecuencia**: Lunes a Viernes
- **Método**: Windows Scheduled Task (scripts ya creados en `scripts/`)

Para configurar:

```bash
# En Windows Server
cd C:\Projects\stock-market
python scripts\setup_task.py
```

## 🧪 Testing

```bash
# Test local sin BD
python test_nuevo_framework.py

# Output esperado:
# ✅ WALMEX incremental: 1 registros
# ✅ ALSEA incremental: 1 registros
# ✅ WALMEX histórico: 251 registros
```

## 📈 Capacidad y Límites

### Yahoo Finance

- **Costo**: GRATIS
- **Límite de requests**: ~2,000/hora (no oficial)
- **Tu uso**: 3-10 requests/día = 0.5% del límite
- **Conclusión**: Capacidad de sobra

### Rendimiento

- **Incremental (1 día)**: ~0.5 segundos
- **Histórico (1 año)**: ~1-2 segundos
- **Batch (10 tickers)**: ~10-20 segundos

## 🛡️ Manejo de Errores

El framework maneja automáticamente:

1. **Conexión a BD**: Retry automático
2. **Duplicados**: UPSERT (no falla)
3. **Datos faltantes**: Log warning, continúa
4. **Yahoo Finance caído**: Exception con mensaje claro

## 📝 Ejemplos de Uso

### Ejemplo 1: Carga Incremental Diaria

```python
from src.etl.walmex import run_incremental

# Ejecutar carga del último día
run_incremental(lookback_days=1)
```

### Ejemplo 2: Backfill de 1 Año

```python
from src.etl.walmex import run_historical

# Cargar 2024 completo
run_historical(
    fecha_inicio="2024-01-01",
    fecha_fin="2024-12-31"
)
```

### Ejemplo 3: Crear Nuevo Ticker

```bash
# 1. Generar estructura
python crear_ticker_etl.py cemex "CEMEXCPO"

# 2. Verificar que el ticker existe en stage.cat_tickers
# 3. Ejecutar histórico
python -m src.etl.cemex.historical --fecha-inicio 2024-01-01

# 4. Configurar en Scheduled Task
```

## 🔧 Mantenimiento

### Agregar Nuevos Campos

Editar `src/etl/shared/models/precio.py`:

```python
@dataclass
class PrecioHistorico:
    # ... campos existentes ...
    nuevo_campo: Optional[str] = None
```

### Cambiar Fuente de Datos

Crear nuevo extractor en `src/etl/shared/extractors/`:

```python
class DataBursatilExtractor:
    def extract_incremental(self):
        # Implementación
        pass
```

Usar en ETL:

```python
from src.etl.shared.extractors import DataBursatilExtractor

extractor = DataBursatilExtractor(...)
precios = extractor.extract_incremental()
```

## 📚 Referencias

- [Yahoo Finance API (yfinance)](https://github.com/ranaroussi/yfinance)
- [Loguru Documentation](https://loguru.readthedocs.io/)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)

## 🎯 Roadmap

- [x] Framework base con Yahoo Finance
- [x] Extractor genérico
- [x] Loader con UPSERT
- [x] ETL para WALMEX
- [x] ETL para ALSEA
- [ ] Agregar más tickers (GFNORTE, CEMEX, AMXL)
- [ ] Scheduled Task en Windows Server
- [ ] Fallback a DataBursátil (opcional)
- [ ] Notificaciones por email en caso de error
- [ ] Dashboard de monitoreo

## 💡 Decisiones de Diseño

### ¿Por qué Yahoo Finance?

1. **Gratis**: Sin costo ni API key
2. **Completo**: OHLCV vs solo último precio
3. **Confiable**: Datos desde ~2000
4. **Simple**: Una sola fuente, menos complejidad

### ¿Por qué un ETL por ticker?

1. **Escalabilidad**: Agregar tickers sin modificar código existente
2. **Debugging**: Fácil identificar qué ticker falla
3. **Scheduling**: Ejecutar tickers en horarios diferentes si es necesario
4. **Mantenimiento**: Cambios en WALMEX no afectan ALSEA

### ¿Por qué UPSERT?

1. **Idempotencia**: Correr el ETL 2 veces no duplica datos
2. **Correcciones**: Si Yahoo actualiza datos históricos, se actualizan en BD
3. **Simplicidad**: No necesitas verificar si existe antes de insertar

## 🤝 Contribuir

Para agregar un nuevo ticker:

1. Usar generador: `python crear_ticker_etl.py <nombre> <simbolo>`
2. Probar localmente: `python test_nuevo_framework.py`
3. Ejecutar histórico: `python -m src.etl.<nombre>.historical`
4. Actualizar `config/tickers_config.yml`
5. Documentar en este README

---

**Creado**: Diciembre 2025  
**Versión**: 1.0  
**Autor**: Stock Market ETL Bot
