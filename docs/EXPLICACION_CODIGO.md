# 📖 Explicación del Código ETL - Versión Simple

## 🎯 Comparación: Multi-Ticker vs Single-Ticker

### **Versión Original (Multi-Ticker)**

```python
# notebooks/bronze/01_ingest_databursatil.ipynb

# PASO 1: Lee TODOS los tickers activos de la base de datos
active_tickers = spark.sql("""
    SELECT ticker FROM silver.tickers 
    WHERE is_active = true
""").collect()
# Resultado: ["WALMEX*", "AMXL", "GFNORTEO", "CEMEXCPO", ...]

# PASO 2: Itera sobre CADA ticker
for ticker in active_tickers:
    # Llamada API individual
    response = api.get("/v2/historicos?emisora_serie={ticker}")
    
    # Guarda CADA respuesta en bronze
    bronze.api_responses.append({
        "ticker": ticker,
        "response_body": response.json(),
        "timestamp": now()
    })

# RESULTADO: N registros en bronze (uno por ticker)
```

**Ventajas:**
- ✅ Procesa todo el mercado de una vez
- ✅ Automatizado para producción

**Desventajas:**
- ❌ Lento (N llamadas API)
- ❌ Difícil debuggear si falla uno
- ❌ Consume muchos créditos

---

### **Versión Simplificada (Single-Ticker)**

```python
# notebooks/bronze/01_ingest_single_ticker.ipynb

# PASO 1: Define ticker específico (hardcoded)
TICKER = "WALMEX*"

# PASO 2: UNA sola llamada API
response = api.get(f"/v2/historicos?emisora_serie={TICKER}")

# PASO 3: Guarda UNA respuesta
bronze.api_responses.append({
    "ticker": TICKER,
    "response_body": response.json(),
    "timestamp": now()
})

# RESULTADO: 1 registro en bronze
```

**Ventajas:**
- ✅ Rápido (1 llamada)
- ✅ Fácil de debuggear
- ✅ Ideal para pruebas
- ✅ Ahorra créditos

**Desventajas:**
- ❌ Solo procesa 1 ticker

---

## 🏗️ Arquitectura Completa del Pipeline

### **Capa 1: BRONZE (Raw Data)**

```
┌─────────────────────────────────────────┐
│  Notebook: 01_ingest_databursatil.ipynb │
├─────────────────────────────────────────┤
│                                         │
│  1. Define ticker(s) a procesar         │
│     • Multi: FROM silver.tickers        │
│     • Single: HARDCODE "WALMEX*"        │
│                                         │
│  2. Llama API DataBursátil              │
│     GET /v2/historicos                  │
│     Params: emisora_serie, inicio,      │
│             final, token                │
│                                         │
│  3. Recibe JSON crudo                   │
│     {                                   │
│       "2025-12-24": {                   │
│         "precio": 68.50,                │
│         "importe": 123456               │
│       },                                │
│       "2025-12-23": {...}               │
│     }                                   │
│                                         │
│  4. Guarda en bronze.api_responses      │
│     Columnas:                           │
│     - response_id (UUID)                │
│     - ticker                            │
│     - endpoint                          │
│     - response_body (JSON string)       │
│     - ingestion_timestamp               │
│     - is_successful                     │
│                                         │
└─────────────────────────────────────────┘
              ↓
    Tabla: bronze.api_responses
    (Delta Lake, partitioned by date)
```

**Código clave:**

```python
# Llamada API
response = requests.get(
    "https://api.databursatil.com/v2/historicos",
    params={
        "token": TOKEN,
        "emisora_serie": "WALMEX*",
        "inicio": "2025-11-01",
        "final": "2025-12-24"
    }
)

# Crear registro
record = {
    "response_id": uuid.uuid4(),
    "ticker": "WALMEX*",
    "endpoint": "/v2/historicos",
    "response_body": response.text,  # JSON crudo
    "is_successful": response.status_code == 200
}

# Guardar en Delta
df = spark.createDataFrame([record])
df.write.format("delta").mode("append").saveAsTable("bronze.api_responses")
```

---

### **Capa 2: SILVER (Cleaned Data)**

```
┌─────────────────────────────────────────┐
│  Notebook: 02_normalize_to_silver.ipynb │
├─────────────────────────────────────────┤
│                                         │
│  1. Lee bronze.api_responses            │
│     WHERE is_successful = true          │
│                                         │
│  2. Parsea JSON                         │
│     De: {"2025-12-24": {"precio": 68}}  │
│     A:  Row(ticker="WALMEX*",           │
│             date="2025-12-24",          │
│             close=68.50)                │
│                                         │
│  3. Aplica calidad de datos             │
│     • Elimina nulls                     │
│     • Elimina duplicados                │
│     • Valida rangos (precio > 0)        │
│                                         │
│  4. MERGE idempotente                   │
│     MERGE INTO silver.market_ohlcv      │
│     ON (ticker, date)                   │
│     WHEN MATCHED UPDATE                 │
│     WHEN NOT MATCHED INSERT             │
│                                         │
└─────────────────────────────────────────┘
              ↓
    Tabla: silver.market_ohlcv
    (Formato largo: 1 fila = 1 ticker + 1 fecha)
```

**Código clave:**

```python
# Lee bronze
bronze_df = spark.sql("""
    SELECT ticker, response_body 
    FROM bronze.api_responses 
    WHERE is_successful = true
""")

# Parsea JSON → filas
parsed = bronze_df.select(
    F.col("ticker"),
    F.explode(F.from_json(F.col("response_body"), schema))
)
# Resultado:
# ticker    | date       | precio
# ----------|------------|-------
# WALMEX*   | 2025-12-24 | 68.50
# WALMEX*   | 2025-12-23 | 68.20
# AMXL      | 2025-12-24 | 15.75

# MERGE (upsert)
DeltaTable.forName(spark, "silver.market_ohlcv") \
    .merge(parsed, "target.ticker = source.ticker AND target.date = source.date") \
    .whenMatchedUpdateAll() \
    .whenNotMatchedInsertAll() \
    .execute()
```

---

### **Capa 3: GOLD (Features para ML)**

```
┌─────────────────────────────────────────┐
│  Notebook: 03_feature_engineering.ipynb │
├─────────────────────────────────────────┤
│                                         │
│  1. Lee silver.market_ohlcv             │
│     Todas las fechas de todos tickers   │
│                                         │
│  2. Agrupa por ticker                   │
│     GROUP BY ticker                     │
│                                         │
│  3. Calcula indicadores técnicos        │
│     Por cada ticker:                    │
│     • SMA (5, 10, 20, 50 días)          │
│     • RSI (14 días)                     │
│     • MACD                              │
│     • Bollinger Bands                   │
│     • Returns (1d, 5d, 20d)             │
│     • Volatility                        │
│                                         │
│  4. Convierte a MAP<string,double>      │
│     {                                   │
│       "sma_5": 68.2,                    │
│       "rsi_14": 55.3,                   │
│       "return_1d": 0.015                │
│     }                                   │
│                                         │
│  5. Guarda en gold.features_daily       │
│     Con features_version para control   │
│                                         │
└─────────────────────────────────────────┘
              ↓
    Tabla: gold.features_daily
    (MAP permite agregar features sin cambiar schema)
```

**Código clave:**

```python
# Lee OHLCV
ohlcv = spark.sql("SELECT * FROM silver.market_ohlcv ORDER BY ticker, date")

# Función de cálculo (pandas)
def calculate_features(pdf):
    pdf['sma_20'] = pdf['close'].rolling(20).mean()
    pdf['rsi_14'] = calculate_rsi(pdf['close'], 14)
    return pdf

# Aplica por ticker
features = ohlcv.groupBy("ticker").applyInPandas(calculate_features, schema)

# Convierte a MAP
features_map = features.select(
    F.col("ticker"),
    F.col("date"),
    F.create_map(
        F.lit("sma_20"), F.col("sma_20"),
        F.lit("rsi_14"), F.col("rsi_14"),
        ...
    ).alias("features")
)

# Guarda
features_map.write.format("delta").saveAsTable("gold.features_daily")
```

---

## 🔄 Flujo de Datos Completo

```
┌─────────────┐
│ DataBursátil│
│     API     │
│             │
│ /v2/        │
│ historicos  │
└──────┬──────┘
       │
       │ JSON: {"2025-12-24": {"precio": 68.50}}
       │
       ↓
┌──────────────────────────────────────┐
│  BRONZE: bronze.api_responses        │
│  ─────────────────────────────────   │
│  response_id | ticker  | response_body│
│  abc-123     | WALMEX* | {"2025..."}  │
│              |         |              │
│  • JSON crudo (audit trail)          │
│  • Partitioned by date               │
└──────┬───────────────────────────────┘
       │
       │ Parse JSON
       │
       ↓
┌──────────────────────────────────────┐
│  SILVER: silver.market_ohlcv         │
│  ─────────────────────────────────   │
│  ticker  | date       | close        │
│  WALMEX* | 2025-12-24 | 68.50        │
│  WALMEX* | 2025-12-23 | 68.20        │
│  AMXL    | 2025-12-24 | 15.75        │
│                                      │
│  • Formato largo (ticker-agnostic)  │
│  • MERGE idempotente                │
│  • PK: (ticker, date)               │
└──────┬───────────────────────────────┘
       │
       │ Calculate features
       │
       ↓
┌──────────────────────────────────────┐
│  GOLD: gold.features_daily           │
│  ─────────────────────────────────   │
│  ticker  | date       | features     │
│  WALMEX* | 2025-12-24 | MAP{sma_20:  │
│          |            |   68.2,      │
│          |            |  rsi_14: 55} │
│                                      │
│  • MAP<string,double> (extensible)  │
│  • features_version control         │
└──────────────────────────────────────┘
```

---

## 🎯 Cómo Usar el Notebook Single-Ticker

### **Paso 1: Configura el ticker**

```python
# Celda 2 del notebook
TICKER_TO_PROCESS = "WALMEX*"  # ← Cambia esto
LOOKBACK_DAYS = 30
TOKEN = "tu_token_aqui"
```

### **Paso 2: Ejecuta todas las celdas**

Hará:
1. Llamada a API
2. Muestra la respuesta
3. Guarda en bronze (Delta o JSON local)

### **Paso 3: Verifica el resultado**

```python
# En Databricks
spark.sql("""
    SELECT * FROM bronze.api_responses 
    WHERE ticker = 'WALMEX*' 
    ORDER BY ingestion_timestamp DESC 
    LIMIT 1
""").show()

# Local
# Revisa archivo: output/WALMEX_bronze.json
```

---

## 💡 Preguntas Frecuentes

### **¿Por qué 3 capas?**

- **Bronze:** Audit trail completo, permite reprocesar
- **Silver:** Datos limpios, formato estándar
- **Gold:** Business logic, listo para ML

### **¿Qué es MERGE idempotente?**

Puedes ejecutar el notebook 1000 veces y siempre tendrás el mismo resultado:

```sql
-- Primera corrida: INSERT
WALMEX*, 2025-12-24, 68.50

-- Segunda corrida: UPDATE (no duplica)
WALMEX*, 2025-12-24, 68.50  -- mismo registro actualizado

-- NO crea:
WALMEX*, 2025-12-24, 68.50
WALMEX*, 2025-12-24, 68.50  ← duplicado
```

### **¿Formato largo vs ancho?**

```python
# ❌ Formato ANCHO (bad practice)
date       | WALMEX_close | AMXL_close | CEMEX_close
2025-12-24 | 68.50        | 15.75      | 12.30

# ✅ Formato LARGO (ticker-agnostic)
ticker   | date       | close
WALMEX*  | 2025-12-24 | 68.50
AMXL     | 2025-12-24 | 15.75
CEMEX    | 2025-12-24 | 12.30
```

Formato largo permite agregar nuevos tickers sin cambiar schema.

---

## 📚 Recursos

- Notebook single-ticker: `notebooks/bronze/01_ingest_single_ticker.ipynb`
- Notebook multi-ticker: `notebooks/bronze/01_ingest_databursatil.ipynb`
- API docs: `docs/API_DATABURSATIL.md`
- Setup guide: `docs/SETUP.md`
