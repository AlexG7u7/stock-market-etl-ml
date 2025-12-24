# Setup Guide - Databricks ETL Pipeline

Esta guía te ayudará a configurar el pipeline ETL completo en Azure Databricks.

---

## 📋 Prerequisitos

- ✅ Cuenta de Azure con acceso a Databricks
- ✅ Token de API de DataBursátil
- ✅ Permisos para crear recursos en Azure
- ✅ Git instalado (para Databricks Repos)

---

## 1️⃣ Configurar Azure Databricks Workspace

### Crear Workspace

```bash
# Via Azure Portal
1. Azure Portal → Create Resource → "Azure Databricks"
2. Resource Group: stock-market-rg
3. Workspace Name: stock-market-dbx
4. Region: East US 2
5. Pricing Tier: Premium (requerido para Unity Catalog)
6. Create
```

### Crear Cluster

```yaml
Cluster Configuration:
  Name: stock-market-cluster
  Runtime: 14.3 LTS (Scala 2.12, Spark 3.5.0)
  Node Type: Standard_DS3_v2 (14 GB, 4 cores)
  Workers: 2-8 (autoscaling)
  
Libraries to Install:
  - pandas-ta
  - requests
  - pyyaml
```

---

## 2️⃣ Configurar Storage (ADLS Gen2)

### Crear Storage Account

```bash
# Azure CLI
az storage account create \
  --name stockmarketdatalake \
  --resource-group stock-market-rg \
  --location eastus2 \
  --sku Standard_LRS \
  --kind StorageV2 \
  --hierarchical-namespace true
```

### Crear Containers

```bash
az storage container create \
  --account-name stockmarketdatalake \
  --name stock-market-data \
  --auth-mode login
```

### Montar en Databricks

```python
# En un notebook de Databricks
configs = {
  "fs.azure.account.auth.type": "OAuth",
  "fs.azure.account.oauth.provider.type": "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
  "fs.azure.account.oauth2.client.id": "<application-id>",
  "fs.azure.account.oauth2.client.secret": dbutils.secrets.get(scope="<scope>", key="<key>"),
  "fs.azure.account.oauth2.client.endpoint": "https://login.microsoftonline.com/<tenant-id>/oauth2/token"
}

dbutils.fs.mount(
  source = "abfss://stock-market-data@stockmarketdatalake.dfs.core.windows.net/",
  mount_point = "/mnt/stock-market",
  extra_configs = configs
)
```

---

## 3️⃣ Configurar Databricks Repos

### Clonar Repositorio

```bash
# En Databricks UI
1. Workspace → Repos → Add Repo
2. Git URL: https://github.com/stock-market-bot/ETL.git
3. Provider: GitHub
4. Repository name: stock-market
5. Create
```

### Estructura esperada

```
/Workspace/Repos/<username>/stock-market/
  ├── config/config.yaml
  ├── notebooks/
  ├── sql/
  └── utils/
```

---

## 4️⃣ Configurar Secrets

### Crear Secret Scope

```bash
# Databricks CLI
databricks secrets create-scope --scope databursatil
```

### Guardar API Token

```bash
# Método interactivo (recomendado)
databricks secrets put --scope databursatil --key api_token

# Se abrirá un editor - pega tu token y guarda
```

### Verificar Secret

```python
# En notebook
token = dbutils.secrets.get(scope="databursatil", key="api_token")
print("✓ Token retrieved successfully")
```

---

## 5️⃣ Crear Bases de Datos y Tablas

### Ejecutar DDL Scripts

```sql
-- 1. Crear databases
CREATE DATABASE IF NOT EXISTS bronze;
CREATE DATABASE IF NOT EXISTS silver;
CREATE DATABASE IF NOT EXISTS gold;

-- 2. Ejecutar DDL scripts en orden
%run /Workspace/Repos/<username>/stock-market/sql/ddl/01_bronze_schema.sql
%run /Workspace/Repos/<username>/stock-market/sql/ddl/02_silver_schema.sql
%run /Workspace/Repos/<username>/stock-market/sql/ddl/03_gold_schema.sql
```

### Verificar Tablas

```sql
-- Ver tablas creadas
SHOW TABLES IN bronze;
SHOW TABLES IN silver;
SHOW TABLES IN gold;

-- Detalles de tabla
DESCRIBE EXTENDED silver.market_ohlcv;
```

---

## 6️⃣ Poblar Catálogo de Tickers

### ⚙️ IMPORTANTE: Ejecutar ANTES del pipeline

El catálogo `silver.tickers` debe poblarse **ANTES** de ejecutar los notebooks de ingesta.

### Opción 1: Automática (Recomendado)

Ejecuta el notebook de setup que llama a la API `/v2/emisoras`:

```python
# Ejecutar: notebooks/setup/00_populate_ticker_catalog.ipynb
# Esto obtiene TODAS las emisoras disponibles en DataBursátil
```

**Ventajas:**
- ✅ Obtiene lista actualizada directamente de la API
- ✅ ~500+ emisoras del mercado mexicano
- ✅ Idempotente (puedes re-ejecutar mensualmente)
- ✅ Costo: ~2-3 créditos de API

**Resultado esperado:**
```
✅ Recibidas 500+ emisoras
✅ Guardadas en silver.tickers con is_active=true
```

### Opción 2: Manual (Testing)

Para pruebas rápidas, puedes insertar solo algunos tickers:

```sql
-- Insertar tickers de ejemplo (top 10 BMV)
INSERT INTO silver.tickers (ticker, is_active, first_seen, last_seen) VALUES
  ('WALMEX*', true, current_timestamp(), current_timestamp()),
  ('AMXL', true, current_timestamp(), current_timestamp()),
  ('GFNORTEO', true, current_timestamp(), current_timestamp()),
  ('CEMEXCPO', true, current_timestamp(), current_timestamp()),
  ('ALFAA', true, current_timestamp(), current_timestamp()),
  ('FEMSAUBD', true, current_timestamp(), current_timestamp()),
  ('GMEXICOB', true, current_timestamp(), current_timestamp()),
  ('BIMBOA', true, current_timestamp(), current_timestamp()),
  ('AC*', true, current_timestamp(), current_timestamp()),
  ('TLEVISACPO', true, current_timestamp(), current_timestamp());

-- Verificar
SELECT COUNT(*) as total_tickers FROM silver.tickers WHERE is_active = true;
```

### Verificar Poblado

```sql
-- Ver total de tickers
SELECT 
  is_active,
  COUNT(*) as total_tickers
FROM silver.tickers
GROUP BY is_active;

-- Ver primeros 10
SELECT ticker, is_active, first_seen
FROM silver.tickers
WHERE is_active = true
ORDER BY ticker
LIMIT 10;
```

---

## 7️⃣ Configurar Workflows (Jobs)

### Crear Job de Ingesta Diaria

```yaml
Job Configuration:
  Name: Daily Market Data Ingestion
  Schedule: Cron: "0 0 * * *" (Daily at midnight)
  Cluster: stock-market-cluster
  
  Tasks:
    - Task 1: Ingest Bronze
      Notebook: /Repos/<username>/stock-market/notebooks/bronze/01_ingest_databursatil.ipynb
      Timeout: 30 minutes
      
    - Task 2: Normalize Silver (depends on Task 1)
      Notebook: /Repos/<username>/stock-market/notebooks/silver/02_normalize_to_silver.ipynb
      Timeout: 20 minutes
      
    - Task 3: Features Gold (depends on Task 2)
      Notebook: /Repos/<username>/stock-market/notebooks/gold/03_feature_engineering.ipynb
      Timeout: 30 minutes
```

---

## 8️⃣ Ejecutar Pipeline por Primera Vez

### Ejecución Manual

```bash
# En Databricks UI - ejecutar notebooks en orden:

1. notebooks/bronze/01_ingest_databursatil.ipynb
   - Fetches last 30 days of data
   - Stores raw JSON in bronze.api_responses
   
2. notebooks/silver/02_normalize_to_silver.ipynb
   - Parses JSON
   - Writes to silver.market_ohlcv
   
3. notebooks/gold/03_feature_engineering.ipynb
   - Calculates technical indicators
   - Writes to gold.features_daily
```

### Validar Resultados

```sql
-- Verificar datos en cada capa
SELECT COUNT(*) FROM bronze.api_responses;
SELECT COUNT(*) FROM silver.market_ohlcv;
SELECT COUNT(*) FROM gold.features_daily;

-- Ver últimos datos
SELECT * FROM silver.market_ohlcv 
WHERE date = (SELECT MAX(date) FROM silver.market_ohlcv)
ORDER BY ticker;
```

---

## 9️⃣ Monitoreo y Alertas

### Configurar Alertas

```yaml
Alerts:
  - Job Failure Notification
    Email: team@example.com
    Trigger: Job fails
    
  - Data Quality Check
    Query: SELECT COUNT(*) FROM silver.market_ohlcv WHERE date = current_date()
    Condition: result < 5
    Action: Send alert
```

---

## 🔧 Troubleshooting

### Problema: Secret no encontrado
```bash
# Verificar scopes
databricks secrets list-scopes

# Verificar secrets en scope
databricks secrets list --scope databursatil
```

### Problema: Delta table no existe
```sql
-- Recrear tabla manualmente
DROP TABLE IF EXISTS silver.market_ohlcv;
-- Ejecutar DDL nuevamente
```

### Problema: Mount point no accesible
```python
# Verificar mount
dbutils.fs.ls("/mnt/stock-market")

# Recrear mount si es necesario
dbutils.fs.unmount("/mnt/stock-market")
# Ejecutar mount nuevamente
```

---

## ✅ Checklist Final

- [ ] Databricks workspace creado
- [ ] Cluster configurado y corriendo
- [ ] ADLS Gen2 storage account creado
- [ ] Mount point configurado
- [ ] Repo clonado en Databricks
- [ ] Secrets configurados
- [ ] Databases y tablas creadas
- [ ] Tickers seed data insertados
- [ ] Pipeline ejecutado exitosamente
- [ ] Workflow/Job configurado
- [ ] Alertas configuradas

---

## 📚 Recursos Adicionales

- [Databricks Documentation](https://docs.databricks.com)
- [Delta Lake Guide](https://docs.delta.io)
- [Azure Databricks Best Practices](https://learn.microsoft.com/azure/databricks/)
- [DataBursátil API Docs](docs/API_DATABURSATIL.md)

---

**¿Necesitas ayuda?** Contacta al equipo en #stock-market-etl
