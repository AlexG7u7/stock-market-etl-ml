# 🛠️ Scripts de Utilidad

Scripts de PowerShell para facilitar el mantenimiento del proyecto en Windows.

## 📋 Scripts Disponibles

### `setup_scheduled_task.ps1` - ⭐ Configurar Tarea Programada ETL

**NUEVO**: Configura Windows Scheduled Task para ejecutar el ETL incremental automáticamente todos los días.

**Qué hace:**
- ✅ Crea Scheduled Task en Windows
- ✅ Configura ejecución diaria a la hora especificada
- ✅ Ejecuta ETL para tickers configurados en `config/tickers_config.yml`
- ✅ Logging automático de todas las ejecuciones

**Uso:**
```powershell
# Ejecutar como Administrador
.\scripts\setup_scheduled_task.ps1

# Personalizar horario (4 PM por defecto)
.\scripts\setup_scheduled_task.ps1 -Hora "16:00"

# Probar ejecución inmediata
Start-ScheduledTask -TaskName "ETL-Incremental-StockMarket"
```

**Ver estado:**
```powershell
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo
```

---

### `setup_env.ps1` - Setup Inicial del Entorno

Configura el entorno completo desde cero. Ejecutar después de clonar el proyecto.

**Qué hace:**
- ✅ Verifica instalación de Python
- ✅ Actualiza pip
- ✅ Instala todas las dependencias desde `requirements.txt`
- ✅ Crea archivo `.env` desde plantilla
- ✅ Verifica conexión a SQL Server
- ✅ Verifica existencia de base de datos
- ✅ Muestra resumen de paquetes instalados

**Uso:**
```powershell
.\scripts\setup_env.ps1
```

---

### `update_deps.ps1` - Actualizar Dependencias

Actualiza las dependencias Python cuando se modifica `requirements.txt`.

**Qué hace:**
- ✅ Actualiza pip
- ✅ Instala/actualiza paquetes desde `requirements.txt`
- ✅ Muestra lista de paquetes actualizados

**Uso:**
```powershell
.\scripts\update_deps.ps1
```

**Cuándo usarlo:**
- Después de hacer `git pull` y ver cambios en `requirements.txt`
- Después de agregar nuevas bibliotecas al proyecto
- Para sincronizar dependencias con otros ambientes

---

## 🚀 Workflow Típico

### Primera vez (Setup inicial):
```powershell
cd C:\Projects\stock-market
.\scripts\setup_env.ps1
```

### Después de git pull:
```powershell
git pull origin main
.\scripts\update_deps.ps1  # Solo si requirements.txt cambió
```

### Agregar nueva biblioteca:

1. Edita `requirements.txt` manualmente
2. Ejecuta:
   ```powershell
   .\scripts\update_deps.ps1
   git add requirements.txt
   git commit -m "feat: Agregar biblioteca X"
   git push origin main
   ```

---

## 📝 Notas

- Todos los scripts asumen que el proyecto está en `C:\Projects\stock-market`
- Los scripts de PowerShell requieren permisos de ejecución
- Si tienes problemas de permisos, ejecuta:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
  
---

## 🤖 Deployment Automático

El deployment se hace automáticamente vía GitHub Actions cuando haces push a `main`. 
Ver documentación en: [docs/WORKFLOWS.md](../docs/WORKFLOWS.md)
