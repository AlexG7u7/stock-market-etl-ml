-- ============================================================================
-- Query para verificar tickers necesarios para el ETL
-- Ejecutar en SQL Server Management Studio o Azure Data Studio
-- ============================================================================

-- 1. Verificar si los 3 tickers existen
-- Nota: emisora_serie se calcula como emisora + serie
SELECT 
    ticker_id,
    emisora,
    serie,
    CONCAT(emisora, serie) as emisora_serie_calculada,
    nombre,
    bolsa,
    activo
FROM stage.cat_tickers
WHERE CONCAT(emisora, serie) IN ('WALMEX*', 'ALSEA*', 'ALFAA')
ORDER BY emisora;

-- Output esperado:
-- ticker_id | emisora | serie | emisora_serie_calculada | nombre              | bolsa | activo
-- ----------|---------|-------|-------------------------|---------------------|-------|-------
-- 12345     | ALFA    | A     | ALFAA                   | Alfa                | BMV   | 1
-- 12346     | ALSEA   | *     | ALSEA*                  | Alsea               | BMV   | 1
-- 12347     | WALMEX  | *     | WALMEX*                 | Wal-Mart de México  | BMV   | 1


-- ============================================================================
-- 2. Si NO existen, insertarlos (ejecutar solo si la query anterior no devuelve resultados)
-- ============================================================================

-- Insertar WALMEX* (solo si no existe)
IF NOT EXISTS (SELECT 1 FROM stage.cat_tickers WHERE emisora = 'WALMEX' AND serie = '*')
BEGIN
    INSERT INTO stage.cat_tickers 
    (emisora, serie, nombre, bolsa, mercado, isin, activo, fecha_carga)
    VALUES 
    ('WALMEX', '*', 'Wal-Mart de México', 'BMV', 'CAPITAL', 'MXP801141016', 1, GETDATE());
    
    PRINT 'WALMEX* insertado - ticker_id: ' + CAST(SCOPE_IDENTITY() AS VARCHAR);
END
ELSE
BEGIN
    PRINT 'WALMEX* ya existe';
END

-- Insertar ALSEA* (solo si no existe)
IF NOT EXISTS (SELECT 1 FROM stage.cat_tickers WHERE emisora = 'ALSEA' AND serie = '*')
BEGIN
    INSERT INTO stage.cat_tickers 
    (emisora, serie, nombre, bolsa, mercado, isin, activo, fecha_carga)
    VALUES 
    ('ALSEA', '*', 'Alsea', 'BMV', 'CAPITAL', 'MXP001311150', 1, GETDATE());
    
    PRINT 'ALSEA* insertado - ticker_id: ' + CAST(SCOPE_IDENTITY() AS VARCHAR);
END
ELSE
BEGIN
    PRINT 'ALSEA* ya existe';
END

-- Verificar ALFAA (debería existir ya)
IF NOT EXISTS (SELECT 1 FROM stage.cat_tickers WHERE emisora = 'ALFA' AND serie = 'A')
BEGIN
    INSERT INTO stage.cat_tickers 
    (emisora, serie, nombre, bolsa, mercado, isin, activo, fecha_carga)
    VALUES 
    ('ALFA', 'A', 'Alfa', 'BMV', 'CAPITAL', 'MXP001391012', 1, GETDATE());
    
    PRINT 'ALFAA insertado - ticker_id: ' + CAST(SCOPE_IDENTITY() AS VARCHAR);
END
ELSE
BEGIN
    PRINT 'ALFAA ya existe';
END


-- ============================================================================
-- 3. Verificar que se insertaron correctamente
-- ============================================================================

SELECT 
    ticker_id,
    emisora,
    serie,
    CONCAT(emisora, serie) as emisora_serie,
    nombre,
    bolsa,
    activo,
    fecha_carga
FROM stage.cat_tickers
WHERE CONCAT(emisora, serie) IN ('WALMEX*', 'ALSEA*', 'ALFAA')
ORDER BY emisora;


-- ============================================================================
-- 4. BONUS: Ver cuántos tickers de BMV tienes
-- ============================================================================

SELECT 
    bolsa,
    COUNT(*) as total_tickers,
    SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END) as activos,
    SUM(CASE WHEN activo = 0 THEN 1 ELSE 0 END) as inactivos
FROM stage.cat_tickers
GROUP BY bolsa
ORDER BY total_tickers DESC;


-- ============================================================================
-- 5. BONUS: Ver si ya hay datos de precios históricos para estos tickers
-- ============================================================================

SELECT 
    CONCAT(t.emisora, t.serie) as emisora_serie,
    COUNT(p.precio_id) as total_registros,
    MIN(p.fecha) as primera_fecha,
    MAX(p.fecha) as ultima_fecha
FROM stage.cat_tickers t
LEFT JOIN stage.precios_historicos p ON t.ticker_id = p.ticker_id
WHERE CONCAT(t.emisora, t.serie) IN ('WALMEX*', 'ALSEA*', 'ALFAA')
GROUP BY CONCAT(t.emisora, t.serie)
ORDER BY CONCAT(t.emisora, t.serie);

-- Output esperado si no hay datos aún:
-- emisora_serie | total_registros | primera_fecha | ultima_fecha
-- --------------|-----------------|---------------|-------------
-- ALFAA         | 247             | 2024-12-19    | 2025-12-26
-- ALSEA*        | 0               | NULL          | NULL
-- WALMEX*       | 0               | NULL          | NULL
