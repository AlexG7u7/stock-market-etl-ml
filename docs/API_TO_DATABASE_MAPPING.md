# 📊 Mapeo API → Modelo de Datos

## Arquitectura: API → STAGE → GOLDEN

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  DataBursatil    │─────▶│    STAGE         │─────▶│     GOLDEN       │
│  API (JSON)      │      │  (Landing        │      │  (Dimensional)   │
│                  │      │   Estructurado)  │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
      |                          |                          |
   Parser Python            Tablas SQL              Star Schema
   (in-memory)              Relacionales            + Features
```

**Cambio importante:** No guardamos JSON crudo. Parseamos directamente a tablas relacionales en STAGE.

---

## � CAPA STAGE (Landing Estructurado)

**Objetivo:** Parsear directamente el JSON de la API a tablas relacionales. No se guarda JSON.

### `stage.emisoras`
Catálogo parseado directamente de `/v2/emisoras`.

**Fuente:** `GET /v2/emisoras`

| Campo | Fuente JSON | Transformación |
|-------|-------------|----------------|
| emisora | Key nivel 1 del JSON | Extraer ticker (ej: "WALMEX") |
| serie | Key nivel 2 del JSON | Extraer serie (ej: "*") |
| emisora_serie | Calculado | `emisora + serie` |
| razon_social | `razon_social` | Directo |
| isin | `isin` | Directo |
| bolsa | `bolsa` | Directo |
| tipo_valor_descripcion | `tipo_valor_descripcion` | Directo |
| tipo_valor_id | `tipo_valor_id` | Directo |
| estatus | `estatus` | Directo |
| acciones_en_circulacion | `acciones_en_circulacion` | Directo |
| rango_historicos | `rango_historicos` | Directo |
| mercado | Calculado | "SIC" in tipo_valor → "global", else "local" |

### `stage.precios`
Precios históricos parseados directamente de `/v2/historicos`.

**Fuente:** `GET /v2/historicos?emisora_serie={ticker}&inicio={date}&final={date}`

| Campo | Fuente JSON | Transformación |
|-------|-------------|----------------|
| emisora_serie | Parámetro del request | Directo |
| fecha | Key del JSON | Parse string → DATE |
| precio | `precio` | Directo |
| importe | `importe` | Directo |
| es_valido | Calculado | `precio > 0 AND importe >= 0` |

### `stage.cotizaciones`
Cotizaciones OHLCV parseadas directamente de `/v2/cotizaciones`.

**Fuente:** `GET /v2/cotizaciones?fecha={date}`

| Campo | Fuente JSON | Transformación |
|-------|-------------|----------------|
| emisora_serie | Key nivel 1 | Directo (ej: "WALMEX*") |
| bolsa | Key nivel 2 | Directo (ej: "BMV") |
| fecha | `f` | Parse string → DATE |
| u | `u` | Directo (último/close) |
| p | `p` | Directo (PPP) |
| a | `a` | Directo (anterior) |
| x | `x` | Directo (máximo/high) |
| n | `n` | Directo (mínimo/low) |
| c | `c` | Directo (cambio %) |
| m | `m` | Directo (cambio $) |
| v | `v` | Directo (volumen) |
| o | `o` | Directo (operaciones) |
| i | `i` | Directo (importe) |
| es_valido | Calculado | `n <= u <= x` |

---

## 🟢 CAPA GOLDEN (Gold - Analítica)

**Objetivo:** Modelo dimensional Star Schema para ML/BI.

### `golden.dim_emisoras`
Dimensión de emisoras (SCD Type 2).

Poblada desde `stage.emisoras`, agregando:
- `emisora_key` (surrogate key)
- `es_ipc` (si pertenece al IPC)
- `es_activa` (si tiene operaciones recientes)
- Tracking de cambios con `fecha_inicio/fin`

### `golden.dim_fecha`
Dimensión calendario (pre-poblada).

Incluye:
- Atributos de fecha (año, mes, día, etc.)
- `es_dia_bursatil` (si hubo operaciones)
- Indicadores de fin de periodo

### `golden.fact_precios`
**Tabla de hechos principal - Precios OHLCV.**

Combina datos de:
- `stage.cotizaciones` (campos completos OHLCV)
- `stage.precios` (históricos simples)

| Campo | Origen | Descripción |
|-------|--------|-------------|
| open | cotizaciones.u anterior | Apertura (precio anterior) |
| high | cotizaciones.x | Máximo del día |
| low | cotizaciones.n | Mínimo del día |
| close | precios.precio o cotizaciones.u | **Cierre (principal)** |
| volume | cotizaciones.v | Volumen operado |
| importe | precios.importe o cotizaciones.i | Importe total |
| ppp | cotizaciones.p | Precio promedio ponderado |

**Lógica de Merge:**
```sql
-- Si existe cotizaciones.u → úsalo como close
-- Si no, usar precios.precio
-- Preferir cotizaciones porque tiene más campos
```

### `golden.fact_features`
Features calculadas para ML.

| feature_name | feature_category | Cálculo |
|--------------|------------------|---------|
| SMA_20 | technical | Media móvil 20 días |
| SMA_50 | technical | Media móvil 50 días |
| RSI_14 | technical | Relative Strength Index |
| MACD | technical | MACD indicator |
| BB_upper | technical | Bollinger Band superior |
| volatilidad_21d | technical | Desv. std. 21 días |
| retorno_1d | technical | (close_t / close_t-1) - 1 |

**Nota:** Estas features se calculan desde `golden.fact_precios`.

### `golden.fact_retornos`
Retornos pre-calculados.

| Campo | Fórmula |
|-------|---------|
| ret_1d | (close_t / close_t-1) - 1 |
| ret_5d | (close_t / close_t-5) - 1 |
| ret_21d | (close_t / close_t-21) - 1 |
| log_ret_1d | ln(close_t / close_t-1) |
| vol_21d | STDEV(log_ret_1d) últimos 21 días |

---

## 🔄 Flujo ETL Completo

### 1️⃣ **API → STAGE** (Parsing directo)

```python
import requests
import pyodbc

# 1. Llamar API
response = requests.get("/v2/historicos", params={
    "token": API_TOKEN,
    "emisora_serie": "WALMEX*",
    "inicio": "2024-01-01",
    "final": "2024-12-31"
})

# 2. Registrar llamada en control.api_calls
api_call_id = cursor.execute("""
    INSERT INTO control.api_calls (endpoint, request_url, status_code, ...)
    OUTPUT INSERTED.id
    VALUES (?, ?, ?, ...)
""", 'historicos', response.url, response.status_code, ...).fetchone()[0]

# 3. Parsear JSON y guardar DIRECTAMENTE en STAGE
json_data = response.json()
registros = 0

for fecha, data in json_data.items():
    cursor.execute("""
        INSERT INTO stage.precios (
            api_call_id, emisora_serie, fecha, precio, importe, es_valido
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, api_call_id, 'WALMEX*', fecha, 
         data['precio'], data['importe'],
         1 if data['precio'] > 0 else 0)
    registros += 1

# 4. Actualizar contador
cursor.execute("""
    UPDATE control.api_calls
    SET registros_insertados = ?
    WHERE id = ?
""", registros, api_call_id)
```

### 2️⃣ **STAGE → GOLDEN** (Transformación dimensional)

```python
# Poblar dimensión de emisoras (si es nuevo ticker)
cursor.execute("""
    MERGE INTO golden.dim_emisoras AS target
    USING stage.emisoras AS source
    ON target.emisora_serie = source.emisora_serie AND target.es_actual = 1
    WHEN NOT MATCHED THEN
        INSERT (emisora_serie, emisora, serie, razon_social, ...)
        VALUES (source.emisora_serie, source.emisora, source.serie, ...);
""")

# Poblar fact_precios
cursor.execute("""
    INSERT INTO golden.fact_precios (
        emisora_key, fecha_key, close, volume, importe, ...
    )
    SELECT 
        de.emisora_key,
        df.fecha_key,
        COALESCE(sc.u, sp.precio) AS close,      -- Priorizar cotizaciones
        COALESCE(sc.v, 0) AS volume,
        COALESCE(sc.i, sp.importe) AS importe,
        ...
    FROM stage.precios sp
    LEFT JOIN stage.cotizaciones sc 
        ON sp.emisora_serie = sc.emisora_serie 
        AND sp.fecha = sc.fecha
    JOIN golden.dim_emisoras de 
        ON de.emisora_serie = sp.emisora_serie AND de.es_actual = 1
    JOIN golden.dim_fecha df 
        ON df.fecha = sp.fecha
    WHERE sp.es_valido = 1
      AND NOT EXISTS (
          SELECT 1 FROM golden.fact_precios fp
          WHERE fp.emisora_key = de.emisora_key 
            AND fp.fecha_key = df.fecha_key
      );
""")
```

### 3️⃣ **GOLDEN → Features** (Cálculos analíticos)

```python
# Calcular features técnicas
cursor.execute("""
    -- SMA_20
    INSERT INTO golden.fact_features (precio_id, emisora_key, fecha_key, feature_name, feature_value)
    SELECT 
        p.precio_id,
        p.emisora_key,
        p.fecha_key,
        'SMA_20',
        AVG(p2.close)
    FROM golden.fact_precios p
    CROSS APPLY (
        SELECT TOP 20 close
        FROM golden.fact_precios
        WHERE emisora_key = p.emisora_key
          AND fecha_key <= p.fecha_key
        ORDER BY fecha_key DESC
    ) p2
    GROUP BY p.precio_id, p.emisora_key, p.fecha_key;
""")
```

---

## 📌 Endpoints Priorizados

### ✅ **Implementar PRIMERO**

| Endpoint | Uso | Prioridad |
|----------|-----|-----------|
| `/v2/emisoras` | Catálogo de tickers | 🔴 CRÍTICO |
| `/v2/historicos` | Precios históricos para LSTM | 🔴 CRÍTICO |
| `/v2/cotizaciones` | Datos diarios OHLCV completos | 🔴 CRÍTICO |

### ⭐ **Implementar DESPUÉS**

| Endpoint | Uso | Prioridad |
|----------|-----|-----------|
| `/v2/intradia` | Para modelos intradía | 🟡 MEDIO |
| `/v2/financieros` | Features fundamentales | 🟡 MEDIO |
| `/v2/indices` | Features macro (IPC, S&P500) | 🟢 BAJO |
| `/v2/divisas` | Features macro (USD/MXN) | 🟢 BAJO |
| `/v2/tasas` | Features macro (TIIE, CETES) | 🟢 BAJO |

---

## 🎯 Ejemplo Completo: WALMEX*

### 1. Llamar API

```bash
GET /v2/historicos?token=xxx&emisora_serie=WALMEX*&inicio=2024-01-01&final=2024-01-31
```

**Respuesta:**
```json
{
  "2024-01-02": {"precio": 45.50, "importe": 1234567.89},
  "2024-01-03": {"precio": 46.20, "importe": 2345678.90}
}
```

### 2. Guardar en CONTROL

```sql
INSERT INTO control.api_calls VALUES (
    'historicos', 
    'https://...', 
    '{"emisora_serie":"WALMEX*",...}',
    200, 
    2,    -- 2 KB = 2 créditos
    187,  -- 187 ms
    0,    -- Se actualiza después
    NULL,
    GETDATE()
);
-- Retorna: id = 42
```

### 3. Parsear DIRECTAMENTE a STAGE

```python
# Parser en Python
for fecha, data in response_json.items():
    INSERT INTO stage.precios VALUES (
        42,  -- api_call_id
        'WALMEX*',
        fecha,  # '2024-01-02'
        data['precio'],  # 45.50
        data['importe'],  # 1234567.89
        1,  # es_valido
        GETDATE()
    )

# Actualizar contador
UPDATE control.api_calls SET registros_insertados = 2 WHERE id = 42
```

### 4. Cargar a GOLDEN

```sql
INSERT INTO golden.fact_precios
SELECT
    de.emisora_key,  -- 1001
    df.fecha_key,    -- 20240102
    NULL AS open,
    sp.precio AS high,
    sp.precio AS low,
    sp.precio AS close,  -- ✅ 45.50
    0 AS volume,
    sp.importe,          -- ✅ 1234567.89
    NULL AS ppp,
    NULL AS operaciones,
    1.0 AS ajuste_factor,
    sp.precio AS close_ajustado
FROM stage.precios sp
JOIN golden.dim_emisoras de ON de.emisora_serie = sp.emisora_serie AND de.es_actual = 1
JOIN golden.dim_fecha df ON df.fecha = sp.fecha
WHERE sp.api_call_id = 42 AND sp.es_valido = 1;
```

### 5. Resultado Final

**stage.precios:**
```
id  | api_call_id | emisora_serie | fecha       | precio  | importe       | es_valido
----|-------------|---------------|-------------|---------|---------------|----------
1   | 42          | WALMEX*       | 2024-01-02  | 45.5000 | 1234567.8900  | 1
2   | 42          | WALMEX*       | 2024-01-03  | 46.2000 | 2345678.9000  | 1
```

**golden.fact_precios:**
```
precio_id | emisora_key | fecha_key | close   | volume | importe
----------|-------------|-----------|---------|--------|---------------
1         | 1001        | 20240102  | 45.5000 | 0      | 1234567.8900
2         | 1001        | 20240103  | 46.2000 | 0      | 2345678.9000
```

---

## 💾 Tamaño Estimado de Datos

**Asumiendo:**
- 50 emisoras del IPC
- 5 años de historia (252 días/año = 1,260 días)
- Datos diarios actualizados

| Capa | Tabla | Registros | Tamaño Estimado |
|------|-------|-----------|-----------------|
| **CONTROL** | api_calls | ~500 llamadas | ~1 MB |
| **CONTROL** | etl_log | ~1,000 procesos | ~2 MB |
| **STAGE** | emisoras | ~50 | <1 MB |
| **STAGE** | precios | 50 × 1,260 = 63,000 | ~10 MB |
| **STAGE** | cotizaciones | 50 × 1,260 = 63,000 | ~15 MB |
| **GOLDEN** | dim_emisoras | ~50 | <1 MB |
| **GOLDEN** | dim_fecha | ~3,650 (10 años) | ~1 MB |
| **GOLDEN** | fact_precios | ~63,000 | ~15 MB |
| **GOLDEN** | fact_features | 63,000 × 10 = 630,000 | ~100 MB |
| **GOLDEN** | fact_retornos | ~63,000 | ~10 MB |
| **TOTAL** | - | **~1,400,000 registros** | **~155 MB** |

✅ **Muy manejable** para SQL Server.

**Comparación con arquitectura de 3 capas (RAW-STAGE-GOLDEN):**
- Con RAW (JSON): ~300 MB
- Sin RAW (actual): **~155 MB** 
- **Ahorro: 48%**

---

## 🚀 Próximos Pasos

1. ✅ Usar el script `sql/01_create_schema_LANDING.sql`
2. Crear módulo Python parser (`src/etl/parsers.py`)
   - Función `parse_emisoras(json_response) → List[dict]`
   - Función `parse_historicos(json_response) → List[dict]`
   - Función `parse_cotizaciones(json_response) → List[dict]`
3. Implementar ETL API → STAGE (`src/etl/loaders.py`)
   - `load_emisoras_to_stage(api_response, api_call_id)`
   - `load_historicos_to_stage(api_response, api_call_id)`
   - `load_cotizaciones_to_stage(api_response, api_call_id)`
4. Implementar ETL STAGE → GOLDEN (`src/etl/transformers.py`)
   - `transform_stage_to_golden_precios()`
   - `calculate_features()`
   - `calculate_returns()`
5. Entrenar modelos LSTM

---

**Flujo resumido:**
```
1. API call → Parser Python (in-memory)
2. INSERT directo a STAGE (tablas relacionales)
3. MERGE/INSERT a GOLDEN (Star Schema)
4. Calcular features y retornos
5. Exportar dataset para LSTM
```

**Ventaja clave:** Simple, rápido, eficiente en almacenamiento. 🚀


