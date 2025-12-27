-- ============================================================================
-- VERIFICAR DATOS CARGADOS
-- ============================================================================

-- 1. Ver últimos registros insertados
SELECT TOP 10
    t.emisora_serie,
    p.fecha,
    p.[open] as apertura,
    p.[high] as maximo,
    p.[low] as minimo,
    p.[close] as cierre,
    p.volume as volumen,
    p.importe,
    p.fecha_carga
FROM stage.precios_historicos p
JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
ORDER BY p.fecha_carga DESC;

-- 2. Ver log de ejecuciones ETL
SELECT TOP 5
    log_id,
    proceso,
    estado,
    fecha_inicio,
    fecha_fin,
    registros_procesados,
    mensaje
FROM control.etl_log
ORDER BY fecha_inicio DESC;

-- 3. Ver datos de ALFAA específicamente
SELECT 
    p.fecha,
    p.[open],
    p.[high],
    p.[low],
    p.[close],
    p.volume,
    p.importe
FROM stage.precios_historicos p
JOIN stage.cat_tickers t ON p.ticker_id = t.ticker_id
WHERE t.emisora_serie = 'ALFAA'
ORDER BY p.fecha DESC;

-- 4. Verificar calendario (días hábiles vs festivos)
SELECT 
    fecha,
    dia_semana_nombre,
    es_fin_semana,
    es_dia_bursatil
FROM stage.cat_calendario
WHERE fecha BETWEEN '2024-12-16' AND '2024-12-27'
ORDER BY fecha;
