# Stock Market ETL Pipeline
## Azure Databricks Medallion Architecture

[![Azure Databricks](https://img.shields.io/badge/Azure-Databricks-FF6C37?logo=databricks)](https://databricks.com)
[![Delta Lake](https://img.shields.io/badge/Delta-Lake-00ADD8?logo=delta)](https://delta.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)

**Plataforma ticker-agnostic, versionable y reproducible** para ingesta, procesamiento y feature engineering de datos de mercado bursátil usando arquitectura Medallion en Azure Databricks.

---

## 🎯 Objetivo

Construir un pipeline ETL robusto que:
- ✅ Ingesta datos de mercado desde API DataBursátil
- ✅ Normaliza y limpia datos en formato largo (ticker-agnostic)
- ✅ Calcula features técnicas para ML (LSTM, portfolio optimization)
- ✅ Versiona datos, código y features para reproducibilidad total
- ✅ Usa Delta Lake como source of truth

## 🏗️ Arquitectura Medallion

```
┌─────────────────────────────────────────────────────────────┐
│  BRONZE: Raw Data                                           │
│  • bronze.api_responses - Raw JSON from DataBursátil API   │
│  • Audit trail completo                                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  SILVER: Cleaned Data                                       │
│  • silver.tickers - Catálogo maestro (ticker-agnostic)     │
│  • silver.market_ohlcv - OHLCV normalizado (long format)   │
│  • MERGE idempotente, PK: (ticker, date)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  GOLD: Business Layer                                       │
│  • gold.features_daily - Features versionadas (MAP format) │
│  • gold.runs - Versionado central (reproducibilidad)       │
│  • gold.predictions - Predicciones LSTM                     │
│  • gold.portfolio_holdings - Portafolios optimizados       │
└─────────────────────────────────────────────────────────────┘
```

## 📂 Estructura del Proyecto

```
stock-market/
├── config/
│   └── config.yaml              # Configuración centralizada
├── notebooks/
│   ├── setup/
│   │   └── 00_populate_ticker_catalog.ipynb  # ⚙️ Setup inicial: Catálogo de tickers
│   ├── bronze/
│   │   ├── 01_ingest_databursatil.ipynb      # Ingesta multi-ticker API → Bronze
│   │   └── 01_ingest_single_ticker.ipynb     # Ingesta single-ticker (testing)
│   ├── silver/
│   │   └── 02_normalize_to_silver.ipynb      # Bronze → Silver
│   └── gold/
│       └── 03_feature_engineering.ipynb      # Silver → Gold
├── sql/
│   └── ddl/
│       ├── 01_bronze_schema.sql            # DDL Bronze layer
│       ├── 02_silver_schema.sql            # DDL Silver layer
│       └── 03_gold_schema.sql              # DDL Gold layer
├── utils/
│   └── databricks_utils.py                 # Utilities compartidas
├── docs/
│   ├── SETUP.md                            # Setup en Databricks
│   ├── API_DATABURSATIL.md                 # Integración API
│   └── EXPLICACION_CODIGO.md               # Explicación arquitectura
├── requirements.txt                        # Dependencias Python
└── README.md                               # Este archivo
```

## 🚀 Quick Start

### 1. Setup en Databricks

```bash
# 1. Clonar repo en Databricks Repos
# En Databricks UI: Repos → Add Repo → https://github.com/stock-market-bot/ETL.git

# 2. Crear bases de datos (ejecutar DDL)
%sql
-- Ejecutar scripts en orden:
-- sql/ddl/01_bronze_schema.sql
-- sql/ddl/02_silver_schema.sql
-- sql/ddl/03_gold_schema.sql
```

### 2. Configurar Secrets

```bash
# Crear secret scope para API token
databricks secrets create-scope --scope databursatil

# Guardar API token
databricks secrets put --scope databursatil --key api_token
```

### 3. Poblar Catálogo de Tickers (Primera vez)

```python
# Ejecutar notebooks/setup/00_populate_ticker_catalog.ipynb
# Esto llena silver.tickers con todas las emisoras disponibles
```

### 4. Ejecutar Pipeline

```python
# Orden de ejecución:
0. notebooks/setup/00_populate_ticker_catalog.ipynb  # ⚙️ Setup inicial (1 vez)
1. notebooks/bronze/01_ingest_databursatil.ipynb     # Ingesta (multi-ticker)
   # O: notebooks/bronze/01_ingest_single_ticker.ipynb (testing)
2. notebooks/silver/02_normalize_to_silver.ipynb     # Normalización
3. notebooks/gold/03_feature_engineering.ipynb       # Features
```

## 📊 Esquema de Datos

### Bronze Layer
```sql
bronze.api_responses
  - response_id (PK)
  - ticker, endpoint, data_date
  - response_body (JSON)
  - ingestion_timestamp
```

### Silver Layer
```sql
silver.tickers
  - ticker (PK)
  - ticker_name, market, sector
  - is_active (boolean)

silver.market_ohlcv
  - ticker, date (PK)
  - open, high, low, close, volume
  - adjusted_close
  - Long format (ticker-agnostic)
```

### Gold Layer
```sql
gold.features_daily
  - ticker, date, features_version (PK)
  - features (MAP<STRING, DOUBLE>)
  - Extensible schema

gold.runs
  - run_id (PK)
  - run_type, features_version
  - data_ref, code_version
  - params_json, metrics_json
  - Central versioning table
```

## 🔄 Versionado y Reproducibilidad

Cada corrida es 100% reproducible usando:

| Campo | Descripción |
|-------|-------------|
| `run_id` | UUID único por ejecución |
| `data_ref` | Delta version o timestamp |
| `features_version` | Versión de lógica de features |
| `code_version` | Git commit SHA |
| `model_version` | MLflow model URI |

**Ejemplo:**
```python
# Reproducir una corrida específica
run = spark.table("gold.runs").filter("run_id = 'abc-123'").first()
features = spark.table("gold.features_daily") \
    .filter(f"features_version = '{run.features_version}'")
```

## 🛠️ Stack Tecnológico

- **Azure Databricks** - Plataforma de procesamiento
- **Delta Lake** - Storage layer con ACID
- **ADLS Gen2** - Data lake storage
- **MLflow** - Tracking y registro de modelos (futuro)
- **Python 3.10+** - Lenguaje principal
- **PySpark** - Procesamiento distribuido
- **pandas-ta** - Indicadores técnicos

## 🎯 Reglas de Diseño

✅ **SI:**
- Formato largo (una fila por ticker-date)
- Delta Lake como source of truth
- JSON/Map para extensibilidad
- Nuevos tickers via `INSERT INTO silver.tickers`
- Idempotencia en todos los notebooks

❌ **NO:**
- Columnas por ticker (anti-patrón)
- SQL Server como source (solo Delta)
- Hard-coding de tickers en código

## 📈 Próximos Pasos

1. **ML Training** - Implementar modelo LSTM
2. **Portfolio Optimization** - Algoritmo de optimización
3. **Databricks Workflows** - Automatización con Jobs
4. **Alerting** - Monitoreo y notificaciones
5. **Unity Catalog** - Governance y permisos

## 📝 Licencia

MIT License - Ver archivo LICENSE para detalles

## 👥 Contribuidores

Stock Market ETL Team - 2025
