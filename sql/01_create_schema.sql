-- ============================================================================
-- MODELO DE DATOS - MERCADO BURSÁTIL MEXICANO
-- Arquitectura: Modelo Relacional Tradicional (sin dimensiones/hechos)
-- Base de datos: SQL Server
-- Fecha: 2024-12-26
-- ============================================================================

USE master;
GO

-- Dropear base de datos si existe (para recrear desde cero)
IF EXISTS (SELECT name FROM sys.databases WHERE name = 'MercadoBursatil')
BEGIN
    ALTER DATABASE MercadoBursatil SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE MercadoBursatil;
    PRINT 'Base de datos MercadoBursatil eliminada';
END
GO

-- Crear base de datos
CREATE DATABASE MercadoBursatil;
PRINT 'Base de datos MercadoBursatil creada';
GO

USE MercadoBursatil;
GO

-- ============================================================================
-- SCHEMAS
-- ============================================================================

-- Schema: control - Auditoría y control de procesos
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'control')
BEGIN
    EXEC('CREATE SCHEMA control');
END
GO

-- Schema: stage - Datos de landing/catálogos maestros
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'stage')
BEGIN
    EXEC('CREATE SCHEMA stage');
END
GO

-- Schema: golden - Datos procesados/analytics
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'golden')
BEGIN
    EXEC('CREATE SCHEMA golden');
END
GO

-- ----------------------------------------------------------------------------
-- Tabla: control.api_calls
-- Propósito: Registro de todas las llamadas a la API DataBursatil
-- ----------------------------------------------------------------------------
IF OBJECT_ID('control.api_calls', 'U') IS NOT NULL
    DROP TABLE control.api_calls;
GO

CREATE TABLE control.api_calls (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    endpoint NVARCHAR(50) NOT NULL,
    request_url NVARCHAR(MAX) NOT NULL,
    request_params_json NVARCHAR(MAX),
    status_code INT NOT NULL,
    creditos_consumidos INT DEFAULT 0,
    response_time_ms INT,
    registros_insertados INT DEFAULT 0,
    error_message NVARCHAR(MAX),
    fecha_request DATETIME2 DEFAULT GETDATE(),
    
    INDEX idx_endpoint (endpoint),
    INDEX idx_fecha_request (fecha_request)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: control.etl_log
-- Propósito: Log de procesos ETL
-- ----------------------------------------------------------------------------
IF OBJECT_ID('control.etl_log', 'U') IS NOT NULL
    DROP TABLE control.etl_log;
GO

CREATE TABLE control.etl_log (
    log_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    proceso NVARCHAR(100) NOT NULL,
    emisora_serie NVARCHAR(30),
    fecha_inicio DATETIME2 NOT NULL,
    fecha_fin DATETIME2,
    registros_procesados INT DEFAULT 0,
    registros_insertados INT DEFAULT 0,
    registros_actualizados INT DEFAULT 0,
    registros_error INT DEFAULT 0,
    estado NVARCHAR(20) NOT NULL,
    mensaje NVARCHAR(MAX),
    created_at DATETIME2 DEFAULT GETDATE(),
    
    INDEX idx_proceso (proceso),
    INDEX idx_estado (estado),
    INDEX idx_fecha_inicio (fecha_inicio)
);
GO

-- ============================================================================
-- SCHEMA STAGE: Catálogos maestros y datos de landing
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Tabla: stage.cat_tickers
-- Propósito: Catálogo maestro de emisoras/tickers
-- ----------------------------------------------------------------------------
IF OBJECT_ID('stage.cat_tickers', 'U') IS NOT NULL
    DROP TABLE stage.cat_tickers;
GO

CREATE TABLE stage.cat_tickers (
    ticker_id INT IDENTITY(1,1) PRIMARY KEY,
    emisora NVARCHAR(20) NOT NULL,
    serie NVARCHAR(10) NOT NULL,
    emisora_serie NVARCHAR(30) NOT NULL UNIQUE,
    razon_social NVARCHAR(500),
    isin NVARCHAR(20),
    bolsa NVARCHAR(100),
    tipo_valor NVARCHAR(200),
    sector NVARCHAR(100),
    subsector NVARCHAR(100),
    es_ipc BIT DEFAULT 0,
    es_activa BIT DEFAULT 1,
    fecha_alta DATETIME2 DEFAULT GETDATE(),
    fecha_baja DATETIME2,
    
    INDEX idx_emisora_serie (emisora_serie),
    INDEX idx_emisora (emisora),
    INDEX idx_es_ipc (es_ipc),
    INDEX idx_es_activa (es_activa)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: stage.cat_calendario
-- Propósito: Catálogo de fechas con atributos de tiempo
-- ----------------------------------------------------------------------------
IF OBJECT_ID('stage.cat_calendario', 'U') IS NOT NULL
    DROP TABLE stage.cat_calendario;
GO

CREATE TABLE stage.cat_calendario (
    fecha DATE PRIMARY KEY,
    anio INT NOT NULL,
    trimestre INT NOT NULL,
    mes INT NOT NULL,
    mes_nombre NVARCHAR(20) NOT NULL,
    semana_anio INT NOT NULL,
    dia_mes INT NOT NULL,
    dia_semana INT NOT NULL,
    dia_semana_nombre NVARCHAR(20) NOT NULL,
    es_fin_semana BIT DEFAULT 0,
    es_dia_bursatil BIT DEFAULT 1,
    es_fin_mes BIT DEFAULT 0,
    es_fin_trimestre BIT DEFAULT 0,
    es_fin_anio BIT DEFAULT 0,
    
    INDEX idx_anio (anio),
    INDEX idx_mes (mes),
    INDEX idx_es_dia_bursatil (es_dia_bursatil)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: stage.precios_historicos
-- Propósito: Precios históricos diarios de cada ticker (landing)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('stage.precios_historicos', 'U') IS NOT NULL
    DROP TABLE stage.precios_historicos;
GO

CREATE TABLE stage.precios_historicos (
    precio_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    fecha DATE NOT NULL,
    [open] DECIMAL(18,4),
    [high] DECIMAL(18,4),
    [low] DECIMAL(18,4),
    [close] DECIMAL(18,4) NOT NULL,
    volume BIGINT,
    importe DECIMAL(22,4),
    ajuste_factor DECIMAL(10,6) DEFAULT 1.0,
    close_ajustado DECIMAL(18,4),
    api_call_id BIGINT,
    fecha_carga DATETIME2 DEFAULT GETDATE(),
    
    CONSTRAINT fk_precios_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    CONSTRAINT fk_precios_fecha FOREIGN KEY (fecha) 
        REFERENCES stage.cat_calendario(fecha),
    CONSTRAINT fk_precios_api FOREIGN KEY (api_call_id) 
        REFERENCES control.api_calls(id),
    
    CONSTRAINT uq_precio_ticker_fecha UNIQUE (ticker_id, fecha),
    
    INDEX idx_ticker_fecha (ticker_id, fecha),
    INDEX idx_fecha (fecha),
    INDEX idx_fecha_carga (fecha_carga)
);
GO

-- ============================================================================
-- SCHEMA GOLDEN: Datos procesados y analytics
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Tabla: golden.indicadores_tecnicos
-- Propósito: Indicadores técnicos calculados (SMA, RSI, etc.)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('golden.indicadores_tecnicos', 'U') IS NOT NULL
    DROP TABLE golden.indicadores_tecnicos;
GO

CREATE TABLE golden.indicadores_tecnicos (
    indicador_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    fecha DATE NOT NULL,
    sma_20 DECIMAL(18,6),
    sma_50 DECIMAL(18,6),
    sma_200 DECIMAL(18,6),
    ema_12 DECIMAL(18,6),
    ema_26 DECIMAL(18,6),
    rsi_14 DECIMAL(10,4),
    macd DECIMAL(18,6),
    macd_signal DECIMAL(18,6),
    volatilidad_21d DECIMAL(18,6),
    fecha_calculo DATETIME2 DEFAULT GETDATE(),
    
    CONSTRAINT fk_indicadores_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    CONSTRAINT fk_indicadores_fecha FOREIGN KEY (fecha) 
        REFERENCES stage.cat_calendario(fecha),
    
    CONSTRAINT uq_indicador_ticker_fecha UNIQUE (ticker_id, fecha),
    
    INDEX idx_ticker_fecha (ticker_id, fecha)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: golden.retornos
-- Propósito: Retornos calculados para diferentes períodos
-- ----------------------------------------------------------------------------
IF OBJECT_ID('golden.retornos', 'U') IS NOT NULL
    DROP TABLE golden.retornos;
GO

CREATE TABLE golden.retornos (
    retorno_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    fecha DATE NOT NULL,
    ret_1d DECIMAL(10,6),
    ret_5d DECIMAL(10,6),
    ret_21d DECIMAL(10,6),
    ret_63d DECIMAL(10,6),
    log_ret_1d DECIMAL(10,6),
    vol_21d DECIMAL(10,6),
    sharpe_21d DECIMAL(10,6),
    fecha_calculo DATETIME2 DEFAULT GETDATE(),
    
    CONSTRAINT fk_retornos_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    CONSTRAINT fk_retornos_fecha FOREIGN KEY (fecha) 
        REFERENCES stage.cat_calendario(fecha),
    
    CONSTRAINT uq_retorno_ticker_fecha UNIQUE (ticker_id, fecha),
    
    INDEX idx_ticker_fecha (ticker_id, fecha)
);
GO

-- ============================================================================
-- VISTAS ÚTILES
-- ============================================================================

-- Vista: Últimos precios de cada ticker activo
IF OBJECT_ID('dbo.v_ultimos_precios', 'V') IS NOT NULL
    DROP VIEW dbo.v_ultimos_precios;
GO

CREATE VIEW dbo.v_ultimos_precios AS
WITH UltimosPreciosRanked AS (
    SELECT 
        t.ticker_id,
        t.emisora_serie,
        t.razon_social,
        p.fecha,
        p.[close],
        p.volume,
        ROW_NUMBER() OVER (PARTITION BY t.ticker_id ORDER BY p.fecha DESC) as rn
    FROM stage.cat_tickers t
    INNER JOIN stage.precios_historicos p ON t.ticker_id = p.ticker_id
    WHERE t.es_activa = 1
)
SELECT 
    ticker_id,
    emisora_serie,
    razon_social,
    fecha,
    [close] AS ultimo_precio,
    volume AS ultimo_volumen
FROM UltimosPreciosRanked
WHERE rn = 1;
GO

-- Vista: Resumen de tickers con estadísticas
IF OBJECT_ID('dbo.v_resumen_tickers', 'V') IS NOT NULL
    DROP VIEW dbo.v_resumen_tickers;
GO

CREATE VIEW dbo.v_resumen_tickers AS
SELECT 
    t.ticker_id,
    t.emisora_serie,
    t.razon_social,
    t.sector,
    t.es_ipc,
    t.es_activa,
    COUNT(p.precio_id) AS total_registros,
    MIN(p.fecha) AS fecha_inicio,
    MAX(p.fecha) AS fecha_fin,
    AVG(p.[close]) AS precio_promedio,
    MIN(p.[close]) AS precio_minimo,
    MAX(p.[close]) AS precio_maximo
FROM stage.cat_tickers t
LEFT JOIN stage.precios_historicos p ON t.ticker_id = p.ticker_id
GROUP BY 
    t.ticker_id,
    t.emisora_serie,
    t.razon_social,
    t.sector,
    t.es_ipc,
    t.es_activa;
GO

-- ============================================================================
-- PROCEDIMIENTO: Poblar calendario
-- ============================================================================

IF OBJECT_ID('dbo.sp_poblar_calendario', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_poblar_calendario;
GO

CREATE PROCEDURE dbo.sp_poblar_calendario
    @fecha_inicio DATE = '2020-01-01',
    @fecha_fin DATE = '2030-12-31'
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @fecha DATE = @fecha_inicio;
    
    WHILE @fecha <= @fecha_fin
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM stage.cat_calendario WHERE fecha = @fecha)
        BEGIN
            INSERT INTO stage.cat_calendario (
                fecha, anio, trimestre, mes, mes_nombre,
                semana_anio, dia_mes, dia_semana, dia_semana_nombre,
                es_fin_semana, es_dia_bursatil,
                es_fin_mes, es_fin_trimestre, es_fin_anio
            )
            VALUES (
                @fecha,
                YEAR(@fecha),
                DATEPART(QUARTER, @fecha),
                MONTH(@fecha),
                DATENAME(MONTH, @fecha),
                DATEPART(WEEK, @fecha),
                DAY(@fecha),
                DATEPART(WEEKDAY, @fecha),
                DATENAME(WEEKDAY, @fecha),
                CASE WHEN DATEPART(WEEKDAY, @fecha) IN (1, 7) THEN 1 ELSE 0 END,
                CASE WHEN DATEPART(WEEKDAY, @fecha) NOT IN (1, 7) THEN 1 ELSE 0 END,
                CASE WHEN @fecha = EOMONTH(@fecha) THEN 1 ELSE 0 END,
                CASE WHEN @fecha = EOMONTH(@fecha) AND DATEPART(QUARTER, @fecha) IN (3, 6, 9, 12) THEN 1 ELSE 0 END,
                CASE WHEN MONTH(@fecha) = 12 AND DAY(@fecha) = 31 THEN 1 ELSE 0 END
            );
        END
        
        SET @fecha = DATEADD(DAY, 1, @fecha);
    END
    
    PRINT 'Calendario poblado desde ' + CAST(@fecha_inicio AS VARCHAR) + ' hasta ' + CAST(@fecha_fin AS VARCHAR);
END
GO

-- Ejecutar procedimiento para poblar calendario
EXEC dbo.sp_poblar_calendario;
GO

PRINT 'Schema creado exitosamente';
PRINT 'Tablas maestras: cat_tickers, cat_calendario';
PRINT 'Tablas de datos: precios_historicos, indicadores_tecnicos, retornos';
PRINT 'Vistas: v_ultimos_precios, v_resumen_tickers';
GO
