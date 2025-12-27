# 🚀 Guía Rápida de Despliegue - Scheduled Task

## Pasos para configurar la tarea programada en Windows Server

### 1️⃣ Conectarse al servidor
```bash
ssh rodrigo@ssh.rod-b-op.com
```

### 2️⃣ Actualizar el código
```powershell
cd C:\Projects\stock-market
git pull
```

Deberías ver:
```
Updating f0233e6..0d62f18
 scripts/setup_scheduled_task.ps1     | xxx ++++++
 scripts/etl-incremental-task.xml     | xxx ++++++
```

### 3️⃣ Ejecutar PowerShell como Administrador
1. Click derecho en el botón de Windows
2. Seleccionar "Windows PowerShell (Admin)"
3. Click "Sí" en el UAC prompt

### 4️⃣ Configurar el Scheduled Task
```powershell
cd C:\Projects\stock-market
.\scripts\setup_scheduled_task.ps1
```

El script te preguntará:
```
¿Deseas ejecutar la tarea ahora para probarla? (S/N)
```
Responde **S** para probar inmediatamente.

### 5️⃣ Verificar que funciona

**Opción A - Ver en Task Scheduler GUI:**
```powershell
taskschd.msc
```
Buscar: **ETL-Incremental-StockMarket**

**Opción B - PowerShell:**
```powershell
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo
```

Deberías ver:
```
LastRunTime        : 26/12/2024 19:35:00  <- Si ejecutaste el test
LastTaskResult     : 0                     <- 0 = éxito
NextRunTime        : 27/12/2024 16:00:00  <- Mañana a las 4 PM
NumberOfMissedRuns : 0
```

### 6️⃣ Verificar datos en la base de datos
```powershell
sqlcmd -S localhost -d MercadoBursatil -U rodrigo -P rodrigo -Q "SELECT TOP 5 * FROM control.etl_log ORDER BY fecha_inicio DESC"
```

Deberías ver la última ejecución del ETL.

---

## ✅ ¡Listo!

La tarea está configurada y se ejecutará automáticamente todos los días a las **4:00 PM** hora local del servidor.

---

## 📊 Comandos útiles

### Ver próxima ejecución
```powershell
(Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo).NextRunTime
```

### Ejecutar manualmente ahora
```powershell
Start-ScheduledTask -TaskName "ETL-Incremental-StockMarket"
```

### Ver estado actual
```powershell
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Format-List
```

### Ver historial de ejecuciones
```powershell
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 10 | 
    Where-Object { $_.Message -like "*ETL-Incremental*" } |
    Format-Table TimeCreated, Message -Wrap
```

### Cambiar horario (ejemplo: 5 PM)
```powershell
.\scripts\setup_scheduled_task.ps1 -Hora "17:00"
```

### Agregar más tickers
Editar el archivo:
```powershell
notepad C:\Projects\stock-market\config\tickers_config.yml
```

Agregar tickers bajo `tickers_activos`:
```yaml
tickers_activos:
  - ALFAA
  - WALMEX*    # Nuevo
  - ALSEA*     # Nuevo
```

Guardar y cerrar. El cambio se aplicará en la próxima ejecución.

---

## 🔍 Troubleshooting

### Si la tarea no aparece:
```powershell
# Verificar que tienes permisos de administrador
([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
```
Debe retornar: `True`

### Si Python no se encuentra:
```powershell
python --version
```
Si falla, verifica la instalación de Python o usa ruta completa en el script.

### Ver logs detallados de la última ejecución:
```powershell
Get-Content C:\Projects\stock-market\logs\etl-*.log -Tail 50
```

---

## ⏰ Horarios sugeridos

- **16:00** (4 PM): Después del cierre del mercado mexicano
- **17:00** (5 PM): Margen de seguridad para que Yahoo Finance actualice
- **18:00** (6 PM): Máximo margen de seguridad

Para cambiar:
```powershell
.\scripts\setup_scheduled_task.ps1 -Hora "17:00"
```
