-- ============================================================================
-- FIX: Recalcular emisora_serie como CONCAT(emisora, serie)
-- ============================================================================
-- Fecha: 2025-12-29
-- Propósito: Corregir la columna emisora_serie para que sea emisora + serie

USE MercadoBursatil;
GO

PRINT '🔧 Recalculando emisora_serie...';
PRINT '';

-- Actualizar emisora_serie = emisora + serie
UPDATE stage.cat_tickers
SET emisora_serie = CONCAT(emisora, serie);

PRINT '✅ Columna emisora_serie actualizada';
PRINT '';

-- Verificar resultados
PRINT '📊 Verificación de tickers actualizados:';
PRINT '';

SELECT 
    ticker_id,
    emisora,
    serie,
    emisora_serie,
    razon_social
FROM stage.cat_tickers
ORDER BY ticker_id;

PRINT '';
PRINT '✅ Corrección completada!';
GO
