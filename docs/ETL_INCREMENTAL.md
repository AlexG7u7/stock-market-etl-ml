# ETL Incremental - Yahoo Finance

## 📋 Resumen

**Estrategia actual: Yahoo Finance para cargas incrementales diarias**

### ✅ **Yahoo Finance** (Incremental diario)
- **Script**: `src/etl/ejecutar_etl_incremental.py`
- **Fuente**: Yahoo Finance (yfinance library)
- **Uso**: Carga incremental diaria automática
- **Ventajas**: 
  - OHLCV completo (apertura, máximo, mínimo, cierre, volumen ajustado)
  - Gratuito, sin API key
  - Datos actualizados diariamente
  - Sin límites de consultas
- **Ideal para**: Mantenimiento diario de datos históricos

### 📊 **DataBursátil** (Opcional - para validación)
- **Script**: `src/etl/ejecutar_etl_incremental_databursatil.py`
- **Fuente**: API de DataBursátil México
- **Uso**: Validación o datos históricos oficiales
- **Ventajas**: 
  - Datos oficiales de la BMV
- **Limitaciones**: 
  - `/v2/cotizaciones` puede tener retraso en actualización
  - Requiere API token
  - Límites de créditos

---

## 🚀 Uso

### Ejecutar Incremental Yahoo Finance (Diario) ⭐

```bash
# Cargar datos de ayer para tickers configurados
cd C:\Projects\stock-market
python src\etl\ejecutar_etl_incremental.py

# Especificar rango de fechas
python src\etl\ejecutar_etl_incremental.py --fecha-inicio 2024-12-20 --fecha-fin 2024-12-26
```

---

## ⚙️ Configuración

### Tickers Activos

Editar `config/tickers_config.yml`:

```yaml
tickers_activos:
  - ALFAA      # Alfa
  - WALMEX*    # Walmart
  - ALSEA*     # Alsea
  - AMXL       # América Móvil
  # ... agregar más

schedule:
  incremental_hour_utc: 22  # 4 PM CDMX
  days_of_week: "1-5"       # Lunes a viernes

incremental:
  lookback_days: 1          # Mirar 1 día atrás
  auto_resume: true
```

### Variables de Entorno

Crear archivo `.env` en el directorio raíz:

```bash
# DataBursátil API
DATABURSATIL_API_TOKEN=tu_token_aqui

# SQL Server
SQL_SERVER=localhost
SQL_DATABASE=MercadoBursatil
SQL_USER=tu_usuario
SQL_PASSWORD=tu_password
```

---

## 📅 Scheduled Task (Windows)

### Configurar Tarea Programada

El **Scheduled Task** ahora ejecuta el script de **DataBursátil**:

```powershell
# Opción 1: Usar script Python (recomendado para SSH)
python scripts\setup_task.py

# Opción 2: Usar batch file
.\scripts\setup_task.bat

# Opción 3: Usar PowerShell
.\scripts\setup_scheduled_task.ps1
```

La tarea se ejecuta:
- **Diariamente a las 4:00 PM** (hora local)
- Script: `ejecutar_etl_incremental_databursatil.py`
- Fuente: **DataBursátil API**

### Verificar Estado

```powershell
# Ver información de la tarea
schtasks /Query /TN "ETL-Incremental-StockMarket" /FO LIST /V

# Ejecutar ahora (testing)
schtasks /Run /TN "ETL-Incremental-StockMarket"

# Ver última ejecución
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo
```

---

## 🔍 Verificar Datos en la BD

```sql
-- Ver últimas ejecuciones del ETL
SELECT TOP 10 
    log_id,
    proceso,
    estado,
    fecha_inicio,
    fecha_fin,
    registros_procesados,
    mensaje
FROM control.etl_log 
ORDER BY fecha_inicio DESC;

-- Ver datos cargados hoy
SELECT 
    t.emisora_serie,
    p.fecha,
    p.precio_cierre,
    p.volumen,
    p.fuente,
    p.fecha_creacion
FROM stage.precios_historicos p
JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
WHERE CAST(p.fecha_creacion AS DATE) = CAST(GETDATE() AS DATE)
ORDER BY t.emisora_serie, p.fecha DESC;

-- Comparar fuentes
SELECT 
    fuente,
    COUNT(*) as total_registros,
    MIN(fecha) as fecha_mas_antigua,
    MAX(fecha) as fecha_mas_reciente
FROM stage.precios_historicos
GROUP BY fuente;
```

---

## 📊 Estrategia Recomendada

### 1. **Carga Inicial** (Una vez)
Use Yahoo Finance para cargar histórico completo:

```bash
python src\etl\cargar_precios.py --todos --fecha-inicio 2020-01-01 --fecha-fin 2024-12-26
```

### 2. **Mantenimiento Diario** (Automático)
Use DataBursátil para datos del día:

- Scheduled Task ejecuta a las 4 PM
- Carga datos de hoy de todos los tickers en `tickers_config.yml`
- Fuente más confiable (DataBursátil)

### 3. **Backfill** (Si falta un día)
Use DataBursátil con fechas específicas:

```bash
python src\etl\ejecutar_etl_incremental_databursatil.py --fecha-inicio 2024-12-23 --fecha-fin 2024-12-26
```

---

## 🐛 Troubleshooting

### Error: "DATABURSATIL_API_TOKEN no encontrado"
- Verificar que `.env` existe en el directorio raíz
- Verificar que la variable está definida correctamente

### Error: "Ticker no encontrado en cat_tickers"
- Primero ejecutar: `python src/etl/cargar_catalogo.py`
- Esto carga el catálogo de tickers desde DataBursátil

### Task Scheduler no ejecuta el script
- Verificar que el usuario tiene permisos de administrador
- Ver logs en Event Viewer: `Microsoft-Windows-TaskScheduler/Operational`
- Ejecutar manualmente para ver errores:
  ```powershell
  schtasks /Run /TN "ETL-Incremental-StockMarket"
  ```

---

## 📚 Referencias

- [DataBursátil API Docs](https://databursatilmexico.com/api/docs)
- [Yahoo Finance Python Library](https://github.com/ranaroussi/yfinance)
- [Windows Task Scheduler](https://docs.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page)

---

## ✅ Checklist de Migración

- [x] Crear `ejecutar_etl_incremental_databursatil.py`
- [x] Actualizar `setup_task.py` para usar nuevo script
- [x] Actualizar workflow de GitHub Actions
- [x] Documentar diferencias entre fuentes
- [ ] Reconfigurar Scheduled Task en servidor Windows
- [ ] Agregar más tickers a `config/tickers_config.yml`
- [ ] Probar ejecución manual
- [ ] Verificar ejecución automática a las 4 PM

