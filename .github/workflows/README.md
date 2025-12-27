# Workflows de GitHub Actions - ETL Stock Market

Este directorio contiene los workflows automatizados para el ETL de datos del mercado bursátil mexicano.

## 📋 Workflows Disponibles

### 1. ETL Incremental Diario (`etl-incremental.yml`)

**Propósito**: Cargar datos diarios de manera automática para mantener la base de datos actualizada.

**Ejecución automática**:
- ⏰ Todos los días a las **4:00 PM hora CDMX** (10 PM UTC)
- 📅 Solo días hábiles (Lunes a Viernes)

**Ejecución manual**:
```yaml
Tickers: ALFAA,WALMEX*,ALSEA*  # Lista separada por comas
Fecha inicio: 2024-12-20       # Opcional, default: ayer
Fecha fin: 2024-12-26          # Opcional, default: hoy
```

**Configuración de tickers activos**:
Los tickers que se procesan automáticamente se configuran en:
```
config/tickers_config.yml
```

Para agregar/quitar tickers del proceso automático, edita este archivo:
```yaml
tickers_activos:
  - ALFAA      # ticker_id: 14912
  - WALMEX*    # Agregar más tickers aquí
  - ALSEA*
```

### 2. ETL Histórico (`etl-historico.yml`)

**Propósito**: Cargar datos históricos completos para uno o más tickers.

**Ejecución**: Solo manual (workflow_dispatch)

**Parámetros requeridos**:
```yaml
Tickers: ALFAA,WALMEX*         # O "TODOS" para todos los tickers
Fecha inicio: 2024-01-01       # Requerido
Fecha fin: 2024-12-26          # Requerido
Límite: 10                     # Opcional, solo si Tickers="TODOS"
```

**Casos de uso**:

1. **Cargar un ticker específico**:
   ```yaml
   Tickers: ALFAA
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   ```

2. **Cargar varios tickers**:
   ```yaml
   Tickers: ALFAA,WALMEX*,ALSEA*
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   ```

3. **Cargar todos los tickers (con límite para testing)**:
   ```yaml
   Tickers: TODOS
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   Límite: 10
   ```

4. **Cargar todos los tickers (sin límite - CUIDADO: toma horas)**:
   ```yaml
   Tickers: TODOS
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   Límite: (dejar vacío)
   ```

## 🚀 Cómo Ejecutar los Workflows

### Desde GitHub Web UI:

1. Ve a la pestaña **Actions** en el repositorio
2. Selecciona el workflow que deseas ejecutar:
   - "ETL Incremental Diario" 
   - "ETL Histórico"
3. Click en **"Run workflow"**
4. Llena los parámetros según necesites
5. Click en **"Run workflow"** (botón verde)

### Desde GitHub CLI:

```bash
# ETL Incremental (manual)
gh workflow run etl-incremental.yml \
  -f tickers="ALFAA,WALMEX*" \
  -f fecha_inicio="2024-12-20" \
  -f fecha_fin="2024-12-26"

# ETL Histórico - Un ticker
gh workflow run etl-historico.yml \
  -f tickers="ALFAA" \
  -f fecha_inicio="2024-01-01" \
  -f fecha_fin="2024-12-26"

# ETL Histórico - Todos (con límite)
gh workflow run etl-historico.yml \
  -f tickers="TODOS" \
  -f fecha_inicio="2024-01-01" \
  -f fecha_fin="2024-12-26" \
  -f limite="10"
```

## 🔧 Configuración

### Variables de Entorno (GitHub Secrets)

Los workflows requieren las siguientes secrets configuradas en el repositorio:

```
DATABURSATIL_API_TOKEN  # Token de API de DataBursátil
SQL_SERVER              # Servidor SQL (ej: localhost o IP)
SQL_DATABASE            # Nombre de la base de datos
SQL_USER                # Usuario SQL
SQL_PASSWORD            # Contraseña SQL
```

Para configurar secrets:
1. Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Agregar cada variable

### Archivo de Configuración: `config/tickers_config.yml`

Este archivo controla el comportamiento del ETL incremental automático:

```yaml
# Lista de tickers que se procesan diariamente
tickers_activos:
  - ALFAA      # ticker_id: 14912
  # Agregar más aquí

# Horario de ejecución
schedule:
  incremental_hour_utc: 22  # 4 PM CDMX
  days_of_week: "1-5"       # Lunes a Viernes

# Configuración incremental
incremental:
  lookback_days: 1          # Cuántos días atrás cargar
  auto_resume: true         # Continuar desde último dato

# Configuración histórica
historical:
  default_start_date: "2024-01-01"
  test_limit: 10
  sleep_between_tickers: 1
```

## 📊 Monitoreo y Logs

### Ver ejecuciones:
1. Ve a la pestaña **Actions**
2. Selecciona el workflow
3. Click en una ejecución específica
4. Expande los pasos para ver logs detallados

### Verificar datos cargados:

El workflow histórico incluye un paso de verificación que muestra:
- Total de registros en `stage.precios_historicos`
- Últimos tickers cargados con sus rangos de fechas

También puedes consultar directamente en SQL Server:

```sql
-- Ver últimas cargas
SELECT TOP 10 * 
FROM control.etl_log 
ORDER BY fecha_inicio DESC;

-- Contar registros por ticker
SELECT 
    t.emisora_serie,
    COUNT(*) as registros,
    MIN(p.fecha) as desde,
    MAX(p.fecha) as hasta
FROM stage.precios_historicos p
JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
GROUP BY t.emisora_serie
ORDER BY MAX(p.fecha) DESC;
```

## 🎯 Estrategia de Uso Recomendada

### Fase 1: Setup Inicial
1. Ejecutar **ETL Histórico** para ALFAA (testing)
   ```yaml
   Tickers: ALFAA
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   ```

2. Verificar datos cargados correctamente

3. Ejecutar **ETL Histórico** para primeros 10 tickers
   ```yaml
   Tickers: TODOS
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   Límite: 10
   ```

### Fase 2: Carga Masiva
4. Ejecutar **ETL Histórico** para todos los tickers
   ```yaml
   Tickers: TODOS
   Fecha inicio: 2024-01-01
   Fecha fin: 2024-12-26
   Límite: (vacío)
   ```
   ⚠️ **Nota**: Esto puede tomar 2-4 horas para ~3500 tickers

### Fase 3: Mantenimiento Diario
5. Configurar tickers activos en `config/tickers_config.yml`

6. El **ETL Incremental** se ejecutará automáticamente cada día hábil a las 4 PM CDMX

7. Monitorear ejecuciones en la pestaña Actions

### Fase 4: Actualizaciones Ad-hoc
8. Usar **ETL Incremental** manual para cargas específicas

9. Usar **ETL Histórico** para rellenar gaps o agregar nuevos tickers

## ⚠️ Troubleshooting

### Error: "No secrets configured"
- Verifica que todas las secrets estén configuradas en GitHub
- Revisa los nombres exactos (case-sensitive)

### Error: "Ticker not found"
- Verifica que el ticker exista en `stage.cat_tickers`
- Usa el formato exacto de `emisora_serie` (ej: `ALFAA`, `WALMEX*`)

### Error: "SQL connection failed"
- Verifica que el runner tenga acceso a la base de datos
- Si usas un servidor local, considera usar self-hosted runner

### Workflow no se ejecuta automáticamente
- Verifica que el cron esté configurado correctamente
- GitHub Actions puede tener delays de hasta 15 minutos en schedules
- Verifica que el repositorio no esté inactivo (debe tener commits recientes)

## 📝 Notas Adicionales

- **Rate Limiting**: Yahoo Finance tiene límites. El script incluye pausas automáticas.
- **Datos duplicados**: El script maneja duplicados con UPDATE/INSERT lógico.
- **Logging**: Todas las ejecuciones se registran en `control.etl_log`.
- **Horario de verano**: Ajusta `incremental_hour_utc` si CDMX cambia a horario de verano.

## 🔗 Referencias

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Cron Expression Helper](https://crontab.guru/)
- [Yahoo Finance API](https://pypi.org/project/yfinance/)
