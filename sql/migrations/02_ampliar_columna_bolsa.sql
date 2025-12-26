-- Migración: Ampliar columna bolsa en stage.cat_tickers
-- Fecha: 2025-12-26
-- Razón: Los nombres de bolsas como "LONDON STOCK EXCHANGE" no caben en NVARCHAR(10)

USE MercadoBursatil;
GO

-- Ampliar columna bolsa de NVARCHAR(10) a NVARCHAR(100)
ALTER TABLE stage.cat_tickers
ALTER COLUMN bolsa NVARCHAR(100);
GO

PRINT '✅ Columna bolsa ampliada a NVARCHAR(100)';
GO
