# Guía de Ejecución - ETL Framework

## 📋 Orden de Ejecución en Servidor Windows

### ✅ Paso 0: Verificar despliegue de GitHub Actions

```powershell
cd C:\Projects\stock-market
git status
git log --oneline -1
```

Deberías ver el commit: `✨ Nuevo framework ETL modular con Yahoo Finance`

---

### ✅ Paso 1: Instalar dependencias

```powershell
# Verificar Python
python --version  # Debe ser 3.13+

# Instalar nuevas dependencias
pip install yfinance loguru
```

---

### ✅ Paso 2: **IMPORTANTE** - Configurar tickers en la BD

**Este paso es OBLIGATORIO antes de ejecutar los ETL**. Los tickers WALMEX* y ALSEA* necesitan existir en `stage.cat_tickers` para que funcione el foreign key en `stage.precios_historicos`.

```powershell
python scripts\setup_tickers.py
```

**Output esperado:**
```
📊 Verificando WALMEX*...
✅ Insertado exitosamente
   ticker_id: 12345
   Nombre: Wal-Mart de México

📊 Verificando ALSEA*...
✅ Insertado exitosamente
   ticker_id: 12346
   Nombre: Alsea

📊 Verificando ALFAA...
✅ Ya existe en la base de datos
   ticker_id: 14912
   Nombre: Alfa
```

---

### ✅ Paso 3: Probar el framework (sin BD)

```powershell
python test_nuevo_framework.py
```

**Output esperado:**
```
✅ WALMEX incremental: 1 registros
✅ ALSEA incremental: 1 registros
✅ WALMEX histórico: 251 registros
```

---

### ✅ Paso 4: Ejecutar carga histórica WALMEX (1 año)

```powershell
python -m src.etl.walmex.historical --fecha-inicio 2024-12-27
```

**Output esperado:**
```
ETL HISTÓRICO - WALMEX
Extrayendo datos históricos de WALMEX*...
Extraídos 251 registros de WALMEX*
Cargando 251 registros a la base de datos...
ETL COMPLETADO EXITOSAMENTE
Insertados: 251
Actualizados: 0
Errores: 0
```

---

### ✅ Paso 5: Ejecutar carga histórica ALSEA (1 año)

```powershell
python -m src.etl.alsea.historical --fecha-inicio 2024-12-27
```

**Output esperado:**
```
ETL HISTÓRICO - ALSEA
Extrayendo datos históricos de ALSEA*...
Extraídos 251 registros de ALSEA*
Cargando 251 registros a la base de datos...
ETL COMPLETADO EXITOSAMENTE
Insertados: 251
Actualizados: 0
Errores: 0
```

---

### ✅ Paso 6: Verificar datos en la BD

```sql
-- Contar registros por ticker
SELECT 
    t.emisora_serie,
    COUNT(*) as total_registros,
    MIN(p.fecha) as primera_fecha,
    MAX(p.fecha) as ultima_fecha
FROM stage.precios_historicos p
INNER JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
WHERE t.emisora_serie IN ('WALMEX*', 'ALSEA*', 'ALFAA')
GROUP BY t.emisora_serie
ORDER BY t.emisora_serie;

-- Verificar últimos registros
SELECT TOP 10 
    t.emisora_serie,
    p.fecha,
    p.[close],
    p.volume
FROM stage.precios_historicos p
INNER JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
WHERE t.emisora_serie = 'WALMEX*'
ORDER BY p.fecha DESC;
```

**Output esperado:**
```
emisora_serie | total_registros | primera_fecha | ultima_fecha
ALFAA         | 247             | 2024-12-19    | 2025-12-26
ALSEA*        | 251             | 2024-12-27    | 2025-12-26
WALMEX*       | 251             | 2024-12-27    | 2025-12-26
```

---

### ✅ Paso 7: Configurar tarea programada (4 PM diaria)

**IMPORTANTE:** Actualizar `scripts\setup_task.py` para usar los nuevos ETL:

El script debe ejecutar:
```powershell
python -m src.etl.walmex.incremental
python -m src.etl.alsea.incremental
python -m src.etl.alfaa.incremental  # (cuando lo creemos)
```

Ejecutar:
```powershell
python scripts\setup_task.py
```

---

### ✅ Paso 8: Probar tarea incremental manualmente

```powershell
# WALMEX - último día
python -m src.etl.walmex.incremental

# ALSEA - último día
python -m src.etl.alsea.incremental
```

**Output esperado:**
```
ETL INCREMENTAL - WALMEX
Extrayendo últimos 1 días de WALMEX*...
Extraídos 1 registros de WALMEX*
Cargando 1 registros a la base de datos...
ETL COMPLETADO EXITOSAMENTE
Insertados: 0
Actualizados: 1  # ← Actualiza porque ya existe
Errores: 0
```

---

## 🚨 Troubleshooting

### Error: "Ticker WALMEX* no encontrado en stage.cat_tickers"

**Solución:** Ejecutar `python scripts\setup_tickers.py`

### Error: "No module named 'yfinance'"

**Solución:** `pip install yfinance loguru`

### Error: "Cannot insert duplicate key"

**Solución:** El UPSERT automático debería manejarlo. Verificar que el unique constraint existe:
```sql
SELECT * FROM sys.indexes 
WHERE object_id = OBJECT_ID('stage.precios_historicos') 
AND name = 'uq_precio_ticker_fecha';
```

### Error: Conexión a SQL Server falla

**Solución:** Verificar `.env` tiene las credenciales correctas:
```
SQL_SERVER=localhost
SQL_DATABASE=MercadoBursatil
SQL_USER=tu_usuario
SQL_PASSWORD=tu_contraseña
```

---

## 📊 Monitoreo

### Verificar logs de ejecución

Los logs se muestran en consola con colores:
- 🟢 **INFO**: Operaciones normales
- 🟡 **WARNING**: Advertencias (ej: sin datos)
- 🔴 **ERROR**: Errores críticos
- 🔵 **SUCCESS**: Operaciones exitosas

### Verificar tarea programada

```powershell
# Ver tareas programadas
schtasks /query /tn "ETL-Incremental-StockMarket" /v /fo list

# Ver último resultado
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo
```

---

## 🔄 Agregar Nuevo Ticker

```powershell
# 1. Generar estructura
python crear_ticker_etl.py gfnorte "GFNORTEO"

# 2. Agregar a BD
# Editar scripts\setup_tickers.py y agregar:
# {
#     'emisora_serie': 'GFNORTEO',
#     'emisora': 'GFNORTE',
#     'serie': 'O',
#     'nombre': 'Grupo Financiero Banorte',
#     'bolsa': 'BMV',
#     'mercado': 'CAPITAL',
#     'isin': 'MXP370711014'
# }

# 3. Ejecutar setup
python scripts\setup_tickers.py

# 4. Cargar histórico
python -m src.etl.gfnorte.historical --fecha-inicio 2024-01-01
```

---

## 📝 Checklist de Implementación

- [ ] Código desplegado desde GitHub Actions
- [ ] Dependencias instaladas (`yfinance`, `loguru`)
- [ ] **Tickers configurados en `stage.cat_tickers`** ← CRÍTICO
- [ ] Test local ejecutado exitosamente
- [ ] WALMEX histórico cargado (251 registros)
- [ ] ALSEA histórico cargado (251 registros)
- [ ] Datos verificados en SQL Server
- [ ] Tarea programada configurada (4 PM)
- [ ] Test incremental ejecutado manualmente
- [ ] Monitoreo funcionando

---

**Última actualización:** 28 de diciembre de 2025  
**Framework versión:** 1.0
