# Verificar Scheduled Task - Comandos útiles

## Ver estado de la tarea
```powershell
schtasks /Query /TN "ETL-Incremental-StockMarket" /FO LIST /V
```

## Ver última ejecución
```powershell
Get-ScheduledTask -TaskName "ETL-Incremental-StockMarket" | Get-ScheduledTaskInfo
```

## Ejecutar manualmente (para probar)
```powershell
schtasks /Run /TN "ETL-Incremental-StockMarket"
```

## Ver logs de Event Viewer
```powershell
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 10 | Where-Object {$_.Message -like "*ETL-Incremental-StockMarket*"}
```

## Ver el batch script que se ejecuta
```powershell
type C:\Projects\stock-market\scripts\ejecutar_etl_incremental.bat
```

## Verificar datos en SQL Server
```sql
-- Ver últimos registros insertados
SELECT TOP 10
    CONCAT(t.emisora, t.serie) as ticker,
    p.fecha,
    p.[close],
    p.volume,
    p.fecha_carga
FROM stage.precios_historicos p
INNER JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
WHERE CONCAT(t.emisora, t.serie) IN ('WALMEX*', 'ALSEA*')
ORDER BY p.fecha_carga DESC;
```
