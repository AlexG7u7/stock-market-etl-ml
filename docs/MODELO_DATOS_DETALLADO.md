# 📐 Modelo de Datos - Mercado Bursátil Mexicano

## 🎯 Visión General

**Modelo Relacional Tradicional** simple y directo para datos del mercado bursátil mexicano.

```
API DataBursatil → Parser Python → SQL Server → LSTM/ML
   JSON Response      Validación       Tablas     Predicciones
```

**Filosofía:**
- ✅ **Simplicidad**: Modelo relacional directo, sin capas complejas
- ✅ **Catálogos maestros**: Tickers y calendario centralizados
- ✅ **Datos transaccionales**: Precios, indicadores y retornos
- ✅ **Auditoría separada**: Schema `control` para logs

---

## 📊 Estructura de la Base de Datos

**Base de datos:** `MercadoBursatil`

### Schemas:
- `control` - Auditoría y logs (2 tablas)
- `dbo` - Catálogos y datos (5 tablas + 2 vistas)

### Total: 7 tablas + 2 vistas

---

## 🔐 SCHEMA: control (Auditoría)

### `control.api_calls`
Registro de todas las llamadas a la API DataBursatil.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | BIGINT PK | ID autoincremental |
| `endpoint` | NVARCHAR(50) | 'emisoras', 'historicos', 'cotizaciones' |
| `request_url` | NVARCHAR(MAX) | URL completa |
| `request_params_json` | NVARCHAR(MAX) | Parámetros JSON |
| `status_code` | INT | Código HTTP (200, 404, 500) |
| `creditos_consumidos` | INT | Créditos API gastados |
| `response_time_ms` | INT | Tiempo de respuesta |
| `registros_insertados` | INT | Registros insertados |
| `error_message` | NVARCHAR(MAX) | Mensaje de error |
| `fecha_request` | DATETIME2 | Timestamp |

**Ejemplo:**
```sql
INSERT INTO control.api_calls (endpoint, status_code, creditos_consumidos, registros_insertados)
VALUES ('historicos', 200, 2, 30);
```

---

### `control.etl_log`
Log de procesos ETL.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `log_id` | BIGINT PK | ID autoincremental |
| `proceso` | NVARCHAR(100) | Nombre del proceso |
| `emisora_serie` | NVARCHAR(30) | Ticker procesado |
| `fecha_inicio` | DATETIME2 | Inicio del proceso |
| `fecha_fin` | DATETIME2 | Fin del proceso |
| `registros_procesados` | INT | Registros leídos |
| `registros_insertados` | INT | Registros insertados |
| `registros_actualizados` | INT | Registros actualizados |
| `registros_error` | INT | Registros con error |
| `estado` | NVARCHAR(20) | 'success', 'error', 'warning' |
| `mensaje` | NVARCHAR(MAX) | Detalles |

---

## 📚 CATÁLOGOS MAESTROS

### `cat_tickers`
Catálogo centralizado de emisoras/tickers.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ticker_id` | INT PK | ID autoincremental |
| `emisora` | NVARCHAR(20) | Ticker sin serie: 'WALMEX' |
| `serie` | NVARCHAR(10) | Serie: '*' |
| `emisora_serie` | NVARCHAR(30) UNIQUE | 'WALMEX*' |
| `razon_social` | NVARCHAR(500) | Nombre legal completo |
| `isin` | NVARCHAR(20) | Código ISIN |
| `bolsa` | NVARCHAR(10) | 'BMV' o 'BIVA' |
| `tipo_valor` | NVARCHAR(200) | 'Acciones ordinarias' |
| `sector` | NVARCHAR(100) | Sector económico |
| `subsector` | NVARCHAR(100) | Subsector |
| `es_ipc` | BIT | ¿Pertenece al IPC? |
| `es_activa` | BIT | ¿Está activa? |
| `fecha_alta` | DATETIME2 | Fecha de registro |
| `fecha_baja` | DATETIME2 | Fecha de baja |

**Ejemplo:**
```sql
INSERT INTO cat_tickers (emisora, serie, emisora_serie, razon_social, es_ipc, es_activa)
VALUES ('WALMEX', '*', 'WALMEX*', 'WAL-MART DE MEXICO, S.A.B. DE C.V.', 1, 1);
```

**Índices:**
- `idx_emisora_serie` (emisora_serie)
- `idx_emisora` (emisora)
- `idx_es_ipc` (es_ipc)

---

### `cat_calendario`
Catálogo de fechas con atributos de tiempo.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `fecha` | DATE PK | Fecha |
| `anio` | INT | 2024 |
| `trimestre` | INT | 1-4 |
| `mes` | INT | 1-12 |
| `mes_nombre` | NVARCHAR(20) | 'Diciembre' |
| `semana_anio` | INT | 1-53 |
| `dia_mes` | INT | 1-31 |
| `dia_semana` | INT | 1-7 |
| `dia_semana_nombre` | NVARCHAR(20) | 'Jueves' |
| `es_fin_semana` | BIT | ¿Sábado/Domingo? |
| `es_dia_bursatil` | BIT | ¿Hubo mercado? |
| `es_fin_mes` | BIT | ¿Último día del mes? |
| `es_fin_trimestre` | BIT | ¿Último día del trimestre? |
| `es_fin_anio` | BIT | ¿31 de diciembre? |

**Poblado automáticamente:**
```sql
EXEC dbo.sp_poblar_calendario @fecha_inicio='2020-01-01', @fecha_fin='2030-12-31';
```

---

## 💰 TABLAS DE DATOS

### `precios_historicos`
Precios históricos OHLCV diarios.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `precio_id` | BIGINT PK | ID autoincremental |
| `ticker_id` | INT FK | → cat_tickers |
| `fecha` | DATE FK | → cat_calendario |
| `open` | DECIMAL(18,4) | Precio apertura |
| `high` | DECIMAL(18,4) | Precio máximo |
| `low` | DECIMAL(18,4) | Precio mínimo |
| `close` | DECIMAL(18,4) | **Precio cierre** |
| `volume` | BIGINT | Volumen (acciones) |
| `importe` | DECIMAL(22,4) | Importe en pesos |
| `ajuste_factor` | DECIMAL(10,6) | Factor de ajuste splits |
| `close_ajustado` | DECIMAL(18,4) | Close ajustado |
| `api_call_id` | BIGINT FK | → control.api_calls |
| `fecha_carga` | DATETIME2 | Timestamp de carga |

**Constraints:**
- UNIQUE (ticker_id, fecha)
- Índices: (ticker_id, fecha), (fecha)

**Ejemplo:**
```sql
INSERT INTO precios_historicos (ticker_id, fecha, close, volume, importe)
VALUES (1, '2024-12-26', 45.50, 12345678, 567890123.45);
```

---

### `indicadores_tecnicos`
Indicadores técnicos pre-calculados (SMA, RSI, MACD, etc.).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `indicador_id` | BIGINT PK | ID autoincremental |
| `ticker_id` | INT FK | → cat_tickers |
| `fecha` | DATE FK | → cat_calendario |
| `sma_20` | DECIMAL(18,6) | Media móvil simple 20 |
| `sma_50` | DECIMAL(18,6) | Media móvil simple 50 |
| `sma_200` | DECIMAL(18,6) | Media móvil simple 200 |
| `ema_12` | DECIMAL(18,6) | Media móvil exponencial 12 |
| `ema_26` | DECIMAL(18,6) | Media móvil exponencial 26 |
| `rsi_14` | DECIMAL(10,4) | RSI 14 períodos |
| `macd` | DECIMAL(18,6) | MACD |
| `macd_signal` | DECIMAL(18,6) | MACD Signal |
| `volatilidad_21d` | DECIMAL(18,6) | Volatilidad 21 días |
| `fecha_calculo` | DATETIME2 | Timestamp cálculo |

**Constraints:**
- UNIQUE (ticker_id, fecha)

**Fórmulas:**
```python
# SMA (Simple Moving Average)
sma_20 = mean(close[-20:])

# RSI (Relative Strength Index)
gains = [max(0, close[i] - close[i-1]) for i in range(-14, 0)]
losses = [max(0, close[i-1] - close[i]) for i in range(-14, 0)]
RS = mean(gains) / mean(losses)
RSI = 100 - (100 / (1 + RS))

# Volatilidad
volatilidad_21d = std(close[-21:])
```

---

### `retornos`
Retornos calculados para diferentes períodos.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `retorno_id` | BIGINT PK | ID autoincremental |
| `ticker_id` | INT FK | → cat_tickers |
| `fecha` | DATE FK | → cat_calendario |
| `ret_1d` | DECIMAL(10,6) | Retorno 1 día |
| `ret_5d` | DECIMAL(10,6) | Retorno 5 días |
| `ret_21d` | DECIMAL(10,6) | Retorno 21 días (1 mes) |
| `ret_63d` | DECIMAL(10,6) | Retorno 63 días (3 meses) |
| `log_ret_1d` | DECIMAL(10,6) | Log-retorno 1 día |
| `vol_21d` | DECIMAL(10,6) | Volatilidad 21 días |
| `sharpe_21d` | DECIMAL(10,6) | Sharpe ratio 21 días |
| `fecha_calculo` | DATETIME2 | Timestamp cálculo |

**Constraints:**
- UNIQUE (ticker_id, fecha)

**Fórmulas:**
```python
# Retorno simple
ret_1d = (close_t / close_t-1) - 1
ret_5d = (close_t / close_t-5) - 1

# Log-retorno (preferido para ML)
log_ret_1d = ln(close_t / close_t-1)

# Volatilidad anualizada
vol_21d = std(log_ret_1d[-21:]) * sqrt(252)

# Sharpe Ratio
sharpe_21d = mean(log_ret_1d[-21:]) / std(log_ret_1d[-21:]) * sqrt(252)
```

---

## 📊 VISTAS

### `v_ultimos_precios`
Último precio disponible de cada ticker activo.

```sql
SELECT 
    ticker_id,
    emisora_serie,
    razon_social,
    fecha,
    ultimo_precio,
    ultimo_volumen
FROM dbo.v_ultimos_precios
WHERE emisora_serie = 'WALMEX*';
```

---

### `v_resumen_tickers`
Estadísticas agregadas por ticker.

```sql
SELECT 
    emisora_serie,
    total_registros,
    fecha_inicio,
    fecha_fin,
    precio_promedio,
    precio_minimo,
    precio_maximo
FROM dbo.v_resumen_tickers
WHERE es_ipc = 1;
```

---

## 🔄 Flujo de Datos Completo

### Ejemplo: Cargar precios de WALMEX* (Enero 2024)

**PASO 1: Llamar API**
```python
response = requests.get(
    'https://api.databursatil.com/v2/historicos',
    params={'emisora_serie': 'WALMEX*', 'inicio': '2024-01-01', 'final': '2024-01-31'}
)
data = response.json()
# {"2024-01-02": {"precio": 45.50, "importe": 567890.12}, ...}
```

**PASO 2: Registrar llamada API**
```python
cursor.execute("""
    INSERT INTO control.api_calls (
        endpoint, request_url, status_code, creditos_consumidos, registros_insertados
    ) VALUES ('historicos', ?, 200, 2, 0)
""", request_url)
api_call_id = cursor.lastrowid
```

**PASO 3: Obtener ticker_id**
```python
cursor.execute("SELECT ticker_id FROM cat_tickers WHERE emisora_serie = 'WALMEX*'")
ticker_id = cursor.fetchone()[0]
```

**PASO 4: Insertar precios**
```python
registros = 0
for fecha_str, valores in data.items():
    cursor.execute("""
        INSERT INTO precios_historicos (
            ticker_id, fecha, close, importe, api_call_id
        ) VALUES (?, ?, ?, ?, ?)
    """, ticker_id, fecha_str, valores['precio'], valores['importe'], api_call_id)
    registros += 1

# Actualizar contador
cursor.execute("""
    UPDATE control.api_calls 
    SET registros_insertados = ? 
    WHERE id = ?
""", registros, api_call_id)
```

**PASO 5: Calcular indicadores**
```python
# Obtener últimos 200 precios
cursor.execute("""
    SELECT fecha, close 
    FROM precios_historicos 
    WHERE ticker_id = ? 
    ORDER BY fecha DESC 
    LIMIT 200
""", ticker_id)
precios = cursor.fetchall()

# Calcular SMA, RSI, etc.
sma_20 = calculate_sma(precios, 20)
rsi_14 = calculate_rsi(precios, 14)

# Insertar
cursor.execute("""
    INSERT INTO indicadores_tecnicos (ticker_id, fecha, sma_20, rsi_14)
    VALUES (?, ?, ?, ?)
""", ticker_id, '2024-01-31', sma_20, rsi_14)
```

**PASO 6: Calcular retornos**
```python
# Retorno 1 día
ret_1d = (close_hoy / close_ayer) - 1
log_ret_1d = np.log(close_hoy / close_ayer)

cursor.execute("""
    INSERT INTO retornos (ticker_id, fecha, ret_1d, log_ret_1d)
    VALUES (?, ?, ?, ?)
""", ticker_id, '2024-01-31', ret_1d, log_ret_1d)
```

**PASO 7: Registrar en ETL log**
```python
cursor.execute("""
    INSERT INTO control.etl_log (
        proceso, emisora_serie, fecha_inicio, fecha_fin,
        registros_procesados, registros_insertados, estado, mensaje
    ) VALUES (
        'carga_historicos', 'WALMEX*', ?, ?, ?, ?, 'success', 
        'Cargados 30 días de precios + indicadores + retornos'
    )
""", start_time, end_time, 30, 30)
```

---

## 🎯 Queries Útiles

### Últimos 30 días de precios de WALMEX*
```sql
SELECT 
    c.fecha,
    c.dia_semana_nombre,
    p.close,
    p.volume,
    i.sma_20,
    i.rsi_14,
    r.ret_1d
FROM precios_historicos p
JOIN cat_tickers t ON p.ticker_id = t.ticker_id
JOIN cat_calendario c ON p.fecha = c.fecha
LEFT JOIN indicadores_tecnicos i ON p.ticker_id = i.ticker_id AND p.fecha = i.fecha
LEFT JOIN retornos r ON p.ticker_id = r.ticker_id AND p.fecha = r.fecha
WHERE t.emisora_serie = 'WALMEX*'
  AND c.es_dia_bursatil = 1
ORDER BY p.fecha DESC
LIMIT 30;
```

### Dataset para LSTM
```sql
SELECT 
    t.emisora_serie,
    p.fecha,
    p.close,
    p.volume,
    i.sma_20,
    i.sma_50,
    i.rsi_14,
    i.macd,
    i.volatilidad_21d,
    r.ret_1d,
    r.ret_5d,
    r.vol_21d,
    LEAD(r.ret_5d, 5) OVER (PARTITION BY t.ticker_id ORDER BY p.fecha) AS target_ret_5d
FROM precios_historicos p
JOIN cat_tickers t ON p.ticker_id = t.ticker_id
LEFT JOIN indicadores_tecnicos i ON p.ticker_id = i.ticker_id AND p.fecha = i.fecha
LEFT JOIN retornos r ON p.ticker_id = r.ticker_id AND p.fecha = r.fecha
WHERE t.es_ipc = 1
  AND p.fecha >= '2020-01-01'
ORDER BY t.emisora_serie, p.fecha;
```

### Tickers sin datos recientes
```sql
SELECT 
    emisora_serie,
    fecha_fin,
    DATEDIFF(day, fecha_fin, GETDATE()) AS dias_sin_datos
FROM v_resumen_tickers
WHERE es_activa = 1
  AND DATEDIFF(day, fecha_fin, GETDATE()) > 7
ORDER BY dias_sin_datos DESC;
```

---

## ✅ Resumen

**Estructura:**
- 2 tablas de control (auditoría)
- 2 catálogos maestros (tickers, calendario)
- 3 tablas de datos (precios, indicadores, retornos)
- 2 vistas (últimos precios, resumen)

**Total: 7 tablas + 2 vistas**

**Ventajas:**
- ✅ Modelo simple y directo
- ✅ Fácil de entender y mantener
- ✅ Queries eficientes con índices
- ✅ Separación clara: control / catálogos / datos
- ✅ Ideal para series temporales y ML

**Próximo paso:** Implementar parsers y loaders en Python 🚀
