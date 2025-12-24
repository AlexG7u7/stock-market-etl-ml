# 🚀 Guía de Ejecución en Databricks

## ✅ Cambios Aplicados

El notebook `00_populate_ticker_catalog.ipynb` ahora está **listo para ejecutarse directamente en Databricks**:

- ✅ Código de Spark **descomentado** (activo)
- ✅ Código local **comentado** (desactivado)
- ✅ Token usando `dbutils.secrets` (producción)
- ✅ MERGE en Delta Lake habilitado

---

## 📋 Orden de Ejecución (Primera Vez)

### **Paso 1: Poblar Catálogo** 📋

```bash
# En Databricks UI:
1. Repos → Tu repo → notebooks/setup/01_populate_ticker_catalog.ipynb
2. Attach a cluster (Runtime 14.3 LTS recomendado)
3. Run All (Ctrl+Shift+Enter)
```

**Lo que hace:**
- Llama a `/v2/emisoras` → Obtiene ~4,864 tickers
- Guarda en `silver.tickers` con MERGE
- Costo: ~2,081 créditos (~1% de cuota mensual)

**Verificación:**
```sql
SELECT COUNT(*) FROM silver.tickers;
-- Resultado esperado: ~4,864
```

---

### **Paso 2: Ingesta Bronze** 📥

```bash
# Multi-ticker (producción)
notebooks/bronze/01_ingest_databursatil.ipynb

# O single-ticker (testing)
notebooks/bronze/01_ingest_single_ticker.ipynb
```

**Lo que hace:**
- Lee `silver.tickers WHERE is_active = true`
- Llama API `/v2/historicos` para cada ticker
- Guarda respuestas crudas en `bronze.api_responses`

---

### **Paso 3: Normalización Silver** 🔄

```bash
notebooks/silver/02_normalize_to_silver.ipynb
```

**Lo que hace:**
- Lee `bronze.api_responses`
- Parsea JSON → OHLCV
- MERGE en `silver.market_ohlcv`

---

### **Paso 4: Features Gold** ⭐

```bash
notebooks/gold/03_feature_engineering.ipynb
```

**Lo que hace:**
- Lee `silver.market_ohlcv`
- Calcula indicadores técnicos (SMA, RSI, MACD, etc.)
- Guarda en `gold.features_daily`

---

## 🔐 Configuración de Secrets (Prerequisito)

**ANTES de ejecutar**, asegúrate de tener el secret configurado:

```bash
# Databricks CLI
databricks secrets create-scope --scope databursatil
databricks secrets put --scope databursatil --key api_token
# Pega: 763d9cdce4895c32fcb2f63358c6de
```

**Verificar en Databricks:**
```python
# En cualquier notebook
token = dbutils.secrets.get(scope="databursatil", key="api_token")
print(f"Token: {token[:10]}...")  # Debe mostrar: 763d9cdce4...
```

---

## 📊 Crear Schemas y Tablas (Prerequisito)

**PASO 0: Setup Inicial** ⚙️

Ejecuta PRIMERO este notebook para crear todas las databases y tablas:

```
notebooks/setup/00_create_schemas_and_tables.ipynb
→ Run All
→ Crea: bronze, silver, gold databases + todas las tablas Delta
```

**Lo que hace:**
- ✅ Crea databases: bronze, silver, gold
- ✅ Crea tabla bronze.api_responses
- ✅ Crea tablas silver.tickers y silver.market_ohlcv
- ✅ Crea tablas gold.runs, features_daily, predictions, portfolio_holdings

**Duración:** ~2 minutos

---

## ⚠️ Notas Importantes

### **Token Hardcodeado vs Secrets**

En `00_populate_ticker_catalog.ipynb` (celda de configuración):

```python
# ✅ PRODUCCIÓN (actual):
TOKEN = dbutils.secrets.get(scope="databursatil", key="api_token")

# ❌ TESTING LOCAL (comentado):
# TOKEN = "763d9cdce4895c32fcb2f63358c6de"
```

Si necesitas probar localmente, **invierte los comentarios**.

---

### **Spark Session**

En Databricks, el código de Spark está **activo**:

```python
# ✅ ACTIVO en Databricks:
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
```

---

### **Guardado Local**

El código de guardado local está **comentado**:

```python
# ❌ DESACTIVADO en Databricks:
"""
import os
os.makedirs("output", exist_ok=True)
with open("output/ticker_catalog.json", "w") as f:
    json.dump(tickers_data, f, indent=2, default=str)
"""
```

---

## 🔄 Frecuencia de Ejecución

| Notebook | Frecuencia | Razón |
|----------|-----------|-------|
| `00_populate_ticker_catalog.ipynb` | 1 vez/mes | Actualizar catálogo de emisoras |
| `01_ingest_databursatil.ipynb` | Diario | Ingesta históricos actualizados |
| `02_normalize_to_silver.ipynb` | Diario | Normalizar nuevos datos |
| `03_feature_engineering.ipynb` | Diario | Calcular features para ML |

---

## ✅ Checklist de Primera Ejecución

- [ ] Secret scope `databursatil` creado
- [ ] API token guardado en secrets
- [ ] Cluster de Databricks iniciado (Runtime 14.3+ LTS)
- [ ] **Paso 0**: `00_create_schemas_and_tables.ipynb` ✅
- [ ] Verificación: `SHOW DATABASES` muestra bronze, silver, gold
- [ ] **Paso 1**: `01_populate_ticker_catalog.ipynb` ✅
- [ ] Verificación: `SELECT COUNT(*) FROM silver.tickers` → ~4,864
- [ ] **Paso 2**: `01_ingest_databursatil.ipynb`
- [ ] **Paso 3**: `02_normalize_to_silver.ipynb`
- [ ] **Paso 4**: `03_feature_engineering.ipynb`

---

## 🆘 Troubleshooting

### Error: "Table silver.tickers not found"
**Solución:** Ejecuta `00_create_schemas_and_tables.ipynb` primero

### Error: "DELTA_MISSING_DELTA_TABLE"
**Solución:** Las tablas no existen, ejecuta `00_create_schemas_and_tables.ipynb`

### Error: "Secret scope databursatil does not exist"
**Solución:** Crea el secret scope con Databricks CLI

### Error: "name 'spark' is not defined"
**Solución:** Asegúrate que estás en Databricks, no local

### Error: "ModuleNotFoundError: No module named 'delta'"
**Solución:** Usa Databricks Runtime 14.3+ LTS (incluye Delta Lake)

---

## 📞 Soporte

Ver documentación completa:
- `docs/SETUP.md` - Setup completo de Databricks
- `docs/API_DATABURSATIL.md` - Integración con API
- `docs/EXPLICACION_CODIGO.md` - Arquitectura del código

---

**Última actualización:** 24 de diciembre de 2025
