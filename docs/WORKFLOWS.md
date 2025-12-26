# 🤖 Workflows Automáticos

Este proyecto usa GitHub Actions con self-hosted runner para ejecutar tareas ETL automáticamente en el servidor Windows.

## 📋 Workflows Disponibles

### 1. **Deploy to Windows Server** (`deploy.yml`)
- **Trigger:** Automático en cada `git push` a `main`
- **Función:** Actualiza el código en el servidor (`git pull`)
- **Uso:** Transparente, se ejecuta automáticamente

### 2. **Actualizar Dependencias** (`update-deps.yml`)
- **Trigger:**
  - Automático cuando cambia `requirements.txt` en `main`
  - Manual desde GitHub Actions
- **Función:** Instala/actualiza paquetes Python en el servidor
- **Uso manual:**
  1. Ve a: https://github.com/stock-market-bot/stock-market-etl-ml/actions/workflows/update-deps.yml
  2. Click en "Run workflow"
  3. Selecciona rama `main`
  4. Click "Run workflow"

### 3. **ETL - Cargar Tickers** (`etl-tickers.yml`)
- **Trigger:** 
  - Manual desde GitHub Actions
  - Programado: Diario a las 8:00 AM
- **Función:** Obtiene catálogo de emisoras/tickers desde DataBursátil y actualiza `stage.cat_tickers`
- **Uso manual:**
  1. Ve a: https://github.com/stock-market-bot/stock-market-etl-ml/actions/workflows/etl-tickers.yml
  2. Click en "Run workflow"
  3. Selecciona rama `main`
  4. Click "Run workflow"

### 4. **ETL - Cargar Precios Históricos** (`etl-precios.yml`)
- **Trigger:**
  - Manual con parámetros
  - Programado: Lunes a Viernes a las 9:00 PM
- **Función:** Descarga precios históricos de tickers y carga a `stage.precios_historicos`
- **Parámetros:**
  - `ticker` (opcional): Ticker específico, vacío = todos
  - `fecha_inicio`: Fecha inicial (YYYY-MM-DD)
  - `fecha_fin`: Fecha final (YYYY-MM-DD)
- **Uso manual:**
  1. Ve a: https://github.com/stock-market-bot/stock-market-etl-ml/actions/workflows/etl-precios.yml
  2. Click en "Run workflow"
  3. Llena los parámetros
  4. Click "Run workflow"

---

## 🔑 Secretos Requeridos

Para que los workflows funcionen, debes configurar estos secretos en GitHub:

| Secret | Descripción |
|--------|-------------|
| `DATABURSATIL_API_TOKEN` | Token de API de DataBursátil |
| `SQL_USER` | Usuario SQL Server (`rodrigo`) |
| `SQL_PASSWORD` | Password SQL Server (`rodrigo`) |

**Configurar en:** https://github.com/stock-market-bot/stock-market-etl-ml/settings/secrets/actions

---

## 📅 Programación Automática

Los workflows ETL se ejecutan automáticamente según este calendario:

| Workflow | Frecuencia | Hora | Días |
|----------|-----------|------|------|
| Deploy | Automático | - | Al push a main |
| Update Deps | Automático | - | Al cambiar requirements.txt |
| Cargar Tickers | Diario | 8:00 AM | Todos |
| Cargar Precios | Diario | 9:00 PM | Lunes-Viernes |

**Nota:** Las horas están en la zona horaria del servidor (UTC por defecto en cron).

---

## 🚀 Ejecutar Workflows Manualmente

### Opción 1: Desde GitHub UI
1. Ve a **Actions** en el repositorio
2. Selecciona el workflow que quieres ejecutar
3. Click en "Run workflow"
4. Llena parámetros (si aplica)
5. Click "Run workflow"

### Opción 2: Desde GitHub CLI
```bash
# Cargar tickers
gh workflow run etl-tickers.yml

# Cargar precios (todos los tickers, últimos 30 días)
gh workflow run etl-precios.yml \
  -f fecha_inicio=2024-12-01 \
  -f fecha_fin=2024-12-31

# Cargar precios (ticker específico)
gh workflow run etl-precios.yml \
  -f ticker=ALFAA \
  -f fecha_inicio=2024-01-01 \
  -f fecha_fin=2024-12-31
```

---

## 📊 Ver Logs y Resultados

1. Ve a **Actions** en GitHub
2. Click en el workflow ejecutado
3. Click en el job ("Cargar catálogo de tickers", etc.)
4. Expande los steps para ver logs detallados

Los logs incluyen:
- ✅ Registros insertados/actualizados
- ⏱️ Tiempo de ejecución
- ❌ Errores (si los hay)
- 📈 Estadísticas de la carga

---

## 🔧 Troubleshooting

### El workflow falla con "API token not found"
- Verifica que `DATABURSATIL_API_TOKEN` esté configurado en GitHub Secrets

### El workflow falla con "SQL connection error"
- Verifica que SQL Server esté corriendo en el servidor
- Confirma que `SQL_USER` y `SQL_PASSWORD` sean correctos

### El workflow no se ejecuta automáticamente
- Verifica que el self-hosted runner esté online
- Ve a Settings → Actions → Runners para confirmar

---

## 📚 Más Información

Ver documentación completa en: [GITHUB_ACTIONS_SETUP.md](./GITHUB_ACTIONS_SETUP.md)
