# 📊 ETL - Datos Bursátiles México

![Deploy Status](https://github.com/stock-market-bot/stock-market-etl-ml/actions/workflows/deploy.yml/badge.svg)
![CI Status](https://github.com/stock-market-bot/stock-market-etl-ml/actions/workflows/ci.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![SQL Server](https://img.shields.io/badge/SQL%20Server-2022-red.svg)

Sistema ETL modular para extracción, transformación y carga de datos del mercado bursátil mexicano usando la API de DataBursatil.com y almacenamiento en SQL Server.

## 🎯 Objetivo

Construir un pipeline de datos robusto y escalable para:
- Descarga histórica de precios OHLCV de emisoras mexicanas (BMV/BIVA)
- Actualización diaria automática de cotizaciones
- Almacenamiento estructurado en SQL Server para análisis y ML
- Base de datos extensible para agregar features de Machine Learning

## 🏗️ Arquitectura

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────────┐
│  DataBursatil   │─────▶│  ETL Python  │─────▶│  SQL Server     │
│  API (JSON)     │      │  (Notebooks) │      │  (Remoto SSH)   │
└─────────────────┘      └──────────────┘      └─────────────────┘
                              │
                              ▼
                         ┌──────────────┐
                         │  Features ML │
                         │  (Extensible)│
                         └──────────────┘
```

## 📁 Estructura del Proyecto

```
stock-market/
├── notebooks/              # Jupyter notebooks para ETL
│   ├── 01_etl_historico.ipynb
│   ├── 02_etl_cotidiano.ipynb
│   ├── 03_exploracion_datos.ipynb
│   ├── 04_gestion_tickers.ipynb
│   └── 05_validacion_calidad.ipynb
│
├── src/                    # Módulos Python reutilizables
│   ├── api/               # Wrapper API DataBursatil
│   ├── etl/               # Lógica ETL (Extract, Transform, Load)
│   ├── db/                # Conexión y modelos SQL Server
│   └── utils/             # Utilidades (config, logs, validación)
│
├── sql/                    # Scripts SQL Server
│   ├── 01_create_schema.sql
│   ├── 02_create_indexes.sql
│   └── 03_stored_procedures.sql
│
├── config/                 # Configuración
│   ├── config.yaml
│   ├── tickers.yaml
│   └── .env.example
│
├── data/                   # Datos locales (gitignore)
├── logs/                   # Logs de ejecución
└── scripts/               # Scripts ejecutables
```

## 🚀 Instalación

### 1. Requisitos Previos

- Python 3.9+
- SQL Server en máquina remota (Windows)
- Cloudflare Tunnel configurado para SSH
- Cuenta en DataBursatil.com (API token)

### 2. Instalación de Dependencias

```bash
# Clonar repositorio
cd ~/Projects/stock-market

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Instalar dependencias
pip install -r requirements.txt

# Instalar cloudflared (macOS)
brew install cloudflare/cloudflare/cloudflared
```

### 3. Configuración

```bash
# Copiar template de configuración
cp config/.env.example config/.env

# Editar credenciales
nano config/.env
```

Variables requeridas en `.env`:
```env
# API DataBursatil
DATABURSATIL_API_TOKEN=tu_token_aqui

# SQL Server
SQL_SERVER_HOST=localhost  # Via SSH tunnel
SQL_SERVER_PORT=1433
SQL_SERVER_DATABASE=MercadoBursatil
SQL_SERVER_USER=sa
SQL_SERVER_PASSWORD=tu_password

# SSH Tunnel (Cloudflare)
SSH_HOSTNAME=ssh.rod-b-op.com
SSH_USER=rodri
SSH_LOCAL_PORT=1433
SSH_REMOTE_PORT=1433
CLOUDFLARE_TUNNEL_ID=5a5dd112-9705-4f62-b97f-c7723daf5afc
```

### 4. Inicializar Base de Datos

```bash
# Conectar vía SSH (Cloudflare Tunnel)
cloudflared access ssh --hostname ssh.rod-b-op.com --user rodri

# Ejecutar scripts SQL
python scripts/setup_database.py
```

## 📊 Uso

### ETL Histórico (Carga Inicial)

```bash
# Desde Jupyter Notebook
jupyter notebook notebooks/01_etl_historico.ipynb

# O desde script
python scripts/run_etl_historico.py --tickers WALMEX*,AMXB,CEMEXCPO --start-date 2020-01-01
```

### ETL Cotidiano (Actualización Diaria)

```bash
# Ejecutar manualmente
python scripts/run_etl_cotidiano.py

# O configurar cron job (lunes-viernes 7pm)
crontab -e
0 19 * * 1-5 cd ~/Projects/stock-market && python scripts/run_etl_cotidiano.py
```

## 🗄️ Esquema de Base de Datos

### Tablas Principales

1. **`emisoras`** - Catálogo de emisoras y series
2. **`precios_historicos`** - Precios OHLCV diarios
3. **`features_ml`** - Features extensibles para ML
4. **`etl_log`** - Registro de ejecuciones ETL

Ver detalles completos en `sql/01_create_schema.sql`

## 🔧 Módulos Principales

### API Client
```python
from src.api.databursatil import DataBursatilAPI

api = DataBursatilAPI(token='tu_token')
historicos = api.get_historicos('WALMEX*', '2024-01-01', '2024-12-31')
```

### Database Connection
```python
from src.db.connection import SQLServerConnection

with SQLServerConnection() as conn:
    df.to_sql('precios_historicos', conn, if_exists='append')
```

### ETL Orchestrator
```python
from src.etl.orchestrator import ETLOrchestrator

etl = ETLOrchestrator(mode='historico')
etl.run(tickers=['WALMEX*', 'AMXB'], start_date='2024-01-01')
```

## 📈 Roadmap

- [x] Diseño arquitectura SQL Server
- [x] Estructura modular del proyecto
- [ ] Conexión SQL Server vía SSH tunnel
- [ ] Wrapper API DataBursatil
- [ ] ETL Histórico (notebooks + módulos)
- [ ] ETL Cotidiano (incremental)
- [ ] Sistema gestión de tickers
- [ ] Testing y validación
- [ ] Documentación completa

## 🤝 Contribución

Este es un proyecto personal para análisis de mercado bursátil mexicano.

## 📝 Licencia

MIT

## 📧 Contacto

Desarrollado para análisis de datos bursátiles y modelos LSTM/AG.

---
**Nota:** Nunca commitear archivos con credenciales (`.env`, tokens API, passwords SQL Server)
