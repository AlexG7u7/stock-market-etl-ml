-- ============================================================================
-- SCHEMA ML: Machine Learning - Modelos, Experimentos, Predicciones
-- ============================================================================
-- Fecha: 2025-12-29
-- Propósito: Almacenar modelos, experimentos, predicciones y métricas de ML

USE MercadoBursatil;
GO

-- Crear schema ml si no existe
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'ml')
BEGIN
    EXEC('CREATE SCHEMA ml');
    PRINT '✅ Schema ml creado';
END
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.model_registry
-- Propósito: Registro de todos los modelos entrenados
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.model_registry', 'U') IS NOT NULL
    DROP TABLE ml.model_registry;
GO

CREATE TABLE ml.model_registry (
    model_id INT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    model_name NVARCHAR(100) NOT NULL,           -- 'LSTM_WALMEX_5d_v1.0'
    model_type NVARCHAR(50) NOT NULL,            -- 'LSTM', 'GRU', 'Transformer'
    version NVARCHAR(20) NOT NULL,               -- 'v1.0', 'v1.1', etc.
    prediction_horizon INT NOT NULL,             -- 5, 10, 15 días
    
    -- Hiperparámetros (JSON)
    hyperparameters NVARCHAR(MAX) NOT NULL,      -- JSON con todos los parámetros
    
    -- Arquitectura
    num_layers INT,
    hidden_units INT,
    dropout_rate DECIMAL(5,4),
    learning_rate DECIMAL(10,8),
    batch_size INT,
    epochs INT,
    sequence_length INT,                         -- Lookback window
    
    -- Features utilizados
    features_used NVARCHAR(MAX),                 -- JSON array: ['close', 'volume', 'rsi', 'macd']
    
    -- Métricas de entrenamiento
    train_rmse DECIMAL(18,6),
    train_mae DECIMAL(18,6),
    train_r2 DECIMAL(10,6),
    val_rmse DECIMAL(18,6),
    val_mae DECIMAL(18,6),
    val_r2 DECIMAL(10,6),
    test_rmse DECIMAL(18,6),
    test_mae DECIMAL(18,6),
    test_r2 DECIMAL(10,6),
    
    -- Métricas financieras
    sharpe_ratio DECIMAL(10,6),
    max_drawdown DECIMAL(10,6),
    win_rate DECIMAL(10,6),                      -- % predicciones correctas de dirección
    
    -- Rango de datos de entrenamiento
    train_start_date DATE NOT NULL,
    train_end_date DATE NOT NULL,
    test_start_date DATE,
    test_end_date DATE,
    
    -- Metadata
    model_file_path NVARCHAR(500),               -- Ruta al archivo .h5 o .pkl
    scaler_file_path NVARCHAR(500),              -- Ruta al scaler guardado
    training_duration_seconds INT,
    
    -- Estado
    status NVARCHAR(20) DEFAULT 'trained',       -- 'trained', 'deployed', 'archived'
    is_production BIT DEFAULT 0,                 -- 1 = modelo en producción
    
    -- Auditoría
    created_by NVARCHAR(100) DEFAULT SYSTEM_USER,
    created_at DATETIME2 DEFAULT GETDATE(),
    deployed_at DATETIME2,
    archived_at DATETIME2,
    
    CONSTRAINT fk_model_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    
    INDEX idx_ticker_horizon (ticker_id, prediction_horizon),
    INDEX idx_status (status),
    INDEX idx_is_production (is_production),
    INDEX idx_created_at (created_at)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.experiments
-- Propósito: Registro de experimentos de optimización (Algoritmo Genético)
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.experiments', 'U') IS NOT NULL
    DROP TABLE ml.experiments;
GO

CREATE TABLE ml.experiments (
    experiment_id INT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    experiment_name NVARCHAR(200) NOT NULL,
    prediction_horizon INT NOT NULL,             -- 5, 10, 15 días
    
    -- Configuración del Algoritmo Genético
    population_size INT NOT NULL,
    num_generations INT NOT NULL,
    mutation_rate DECIMAL(5,4),
    crossover_rate DECIMAL(5,4),
    elitism_count INT,
    
    -- Espacio de búsqueda (JSON)
    search_space NVARCHAR(MAX) NOT NULL,         -- JSON con rangos de hiperparámetros
    
    -- Mejor individuo encontrado
    best_model_id INT,                           -- FK a ml.model_registry
    best_fitness DECIMAL(18,6),
    best_hyperparameters NVARCHAR(MAX),
    
    -- Metadata
    start_time DATETIME2 DEFAULT GETDATE(),
    end_time DATETIME2,
    duration_minutes INT,
    total_models_trained INT,
    
    status NVARCHAR(20) DEFAULT 'running',       -- 'running', 'completed', 'failed'
    error_message NVARCHAR(MAX),
    
    created_by NVARCHAR(100) DEFAULT SYSTEM_USER,
    
    CONSTRAINT fk_experiment_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    CONSTRAINT fk_experiment_best_model FOREIGN KEY (best_model_id) 
        REFERENCES ml.model_registry(model_id),
    
    INDEX idx_ticker_horizon (ticker_id, prediction_horizon),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.experiment_generations
-- Propósito: Registro de cada generación en el Algoritmo Genético
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.experiment_generations', 'U') IS NOT NULL
    DROP TABLE ml.experiment_generations;
GO

CREATE TABLE ml.experiment_generations (
    generation_id INT IDENTITY(1,1) PRIMARY KEY,
    experiment_id INT NOT NULL,
    generation_number INT NOT NULL,
    
    -- Estadísticas de la generación
    best_fitness DECIMAL(18,6),
    avg_fitness DECIMAL(18,6),
    worst_fitness DECIMAL(18,6),
    std_fitness DECIMAL(18,6),
    
    -- Mejor individuo de esta generación
    best_hyperparameters NVARCHAR(MAX),
    
    created_at DATETIME2 DEFAULT GETDATE(),
    
    CONSTRAINT fk_generation_experiment FOREIGN KEY (experiment_id) 
        REFERENCES ml.experiments(experiment_id) ON DELETE CASCADE,
    
    INDEX idx_experiment_generation (experiment_id, generation_number)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.predictions
-- Propósito: Almacenar predicciones generadas por modelos
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.predictions', 'U') IS NOT NULL
    DROP TABLE ml.predictions;
GO

CREATE TABLE ml.predictions (
    prediction_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    model_id INT NOT NULL,
    ticker_id INT NOT NULL,
    
    -- Predicción
    prediction_date DATE NOT NULL,               -- Fecha en que se hizo la predicción
    target_date DATE NOT NULL,                   -- Fecha que se está prediciendo
    days_ahead INT NOT NULL,                     -- 1, 2, 3... hasta 15
    
    predicted_close DECIMAL(18,4) NOT NULL,
    predicted_direction NVARCHAR(10),            -- 'UP', 'DOWN', 'NEUTRAL'
    confidence DECIMAL(5,4),                     -- 0.0 a 1.0
    
    -- Valor real (se llena después cuando existe)
    actual_close DECIMAL(18,4),
    actual_direction NVARCHAR(10),
    
    -- Métricas de error
    absolute_error DECIMAL(18,4),
    percentage_error DECIMAL(10,4),
    direction_correct BIT,
    
    -- Metadata
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2,                        -- Cuando se actualiza con valor real
    
    CONSTRAINT fk_prediction_model FOREIGN KEY (model_id) 
        REFERENCES ml.model_registry(model_id),
    CONSTRAINT fk_prediction_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    
    CONSTRAINT uq_prediction UNIQUE (model_id, prediction_date, target_date),
    
    INDEX idx_model_date (model_id, prediction_date),
    INDEX idx_ticker_target_date (ticker_id, target_date),
    INDEX idx_created_at (created_at)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.ab_tests
-- Propósito: Registro de A/B tests entre modelos
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.ab_tests', 'U') IS NOT NULL
    DROP TABLE ml.ab_tests;
GO

CREATE TABLE ml.ab_tests (
    ab_test_id INT IDENTITY(1,1) PRIMARY KEY,
    ticker_id INT NOT NULL,
    prediction_horizon INT NOT NULL,
    
    -- Modelos a comparar
    model_a_id INT NOT NULL,                     -- Modelo actual en producción
    model_b_id INT NOT NULL,                     -- Modelo challenger
    
    -- Período de evaluación
    test_start_date DATE NOT NULL,
    test_end_date DATE NOT NULL,
    
    -- Métricas de modelo A (producción)
    model_a_rmse DECIMAL(18,6),
    model_a_mae DECIMAL(18,6),
    model_a_win_rate DECIMAL(10,6),
    model_a_sharpe DECIMAL(10,6),
    
    -- Métricas de modelo B (challenger)
    model_b_rmse DECIMAL(18,6),
    model_b_mae DECIMAL(18,6),
    model_b_win_rate DECIMAL(10,6),
    model_b_sharpe DECIMAL(10,6),
    
    -- Decisión
    winner NVARCHAR(10),                         -- 'MODEL_A', 'MODEL_B', 'TIE'
    improvement_percentage DECIMAL(10,4),
    deployed BIT DEFAULT 0,                      -- Si se desplegó el challenger
    
    -- Metadata
    created_at DATETIME2 DEFAULT GETDATE(),
    evaluated_at DATETIME2,
    deployed_at DATETIME2,
    
    CONSTRAINT fk_abtest_ticker FOREIGN KEY (ticker_id) 
        REFERENCES stage.cat_tickers(ticker_id),
    CONSTRAINT fk_abtest_model_a FOREIGN KEY (model_a_id) 
        REFERENCES ml.model_registry(model_id),
    CONSTRAINT fk_abtest_model_b FOREIGN KEY (model_b_id) 
        REFERENCES ml.model_registry(model_id),
    
    INDEX idx_ticker_horizon (ticker_id, prediction_horizon),
    INDEX idx_created_at (created_at)
);
GO

-- ----------------------------------------------------------------------------
-- Tabla: ml.feature_importance
-- Propósito: Importancia de features para cada modelo
-- ----------------------------------------------------------------------------
IF OBJECT_ID('ml.feature_importance', 'U') IS NOT NULL
    DROP TABLE ml.feature_importance;
GO

CREATE TABLE ml.feature_importance (
    importance_id INT IDENTITY(1,1) PRIMARY KEY,
    model_id INT NOT NULL,
    feature_name NVARCHAR(100) NOT NULL,
    importance_score DECIMAL(10,6),
    rank INT,
    
    CONSTRAINT fk_importance_model FOREIGN KEY (model_id) 
        REFERENCES ml.model_registry(model_id) ON DELETE CASCADE,
    
    INDEX idx_model_rank (model_id, rank)
);
GO

-- ============================================================================
-- VISTAS ÚTILES PARA ML
-- ============================================================================

-- Vista: Modelos en producción por ticker
IF OBJECT_ID('ml.v_production_models', 'V') IS NOT NULL
    DROP VIEW ml.v_production_models;
GO

CREATE VIEW ml.v_production_models AS
SELECT 
    m.model_id,
    m.model_name,
    t.emisora,
    t.serie,
    CONCAT(t.emisora, t.serie) as ticker,
    m.prediction_horizon,
    m.test_rmse,
    m.test_mae,
    m.sharpe_ratio,
    m.win_rate,
    m.deployed_at,
    DATEDIFF(day, m.deployed_at, GETDATE()) as days_in_production
FROM ml.model_registry m
JOIN stage.cat_tickers t ON m.ticker_id = t.ticker_id
WHERE m.is_production = 1
    AND m.status = 'deployed';
GO

-- Vista: Performance de predicciones por modelo
IF OBJECT_ID('ml.v_prediction_performance', 'V') IS NOT NULL
    DROP VIEW ml.v_prediction_performance;
GO

CREATE VIEW ml.v_prediction_performance AS
SELECT 
    p.model_id,
    m.model_name,
    p.ticker_id,
    p.days_ahead,
    COUNT(*) as total_predictions,
    COUNT(p.actual_close) as evaluated_predictions,
    AVG(p.absolute_error) as avg_absolute_error,
    AVG(p.percentage_error) as avg_percentage_error,
    SUM(CAST(p.direction_correct AS INT)) * 100.0 / COUNT(p.actual_close) as direction_accuracy,
    MIN(p.prediction_date) as first_prediction,
    MAX(p.prediction_date) as last_prediction
FROM ml.predictions p
JOIN ml.model_registry m ON p.model_id = m.model_id
WHERE p.actual_close IS NOT NULL
GROUP BY 
    p.model_id,
    m.model_name,
    p.ticker_id,
    p.days_ahead;
GO

-- ============================================================================
-- PROCEDIMIENTOS ALMACENADOS
-- ============================================================================

-- SP: Desplegar modelo a producción (marca anterior como archived)
IF OBJECT_ID('ml.sp_deploy_model', 'P') IS NOT NULL
    DROP PROCEDURE ml.sp_deploy_model;
GO

CREATE PROCEDURE ml.sp_deploy_model
    @model_id INT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @ticker_id INT, @prediction_horizon INT;
    
    -- Obtener ticker y horizonte del modelo
    SELECT @ticker_id = ticker_id, @prediction_horizon = prediction_horizon
    FROM ml.model_registry
    WHERE model_id = @model_id;
    
    BEGIN TRANSACTION;
    
    TRY
        -- Archivar modelos anteriores en producción para este ticker/horizonte
        UPDATE ml.model_registry
        SET is_production = 0,
            status = 'archived',
            archived_at = GETDATE()
        WHERE ticker_id = @ticker_id
            AND prediction_horizon = @prediction_horizon
            AND is_production = 1;
        
        -- Desplegar nuevo modelo
        UPDATE ml.model_registry
        SET is_production = 1,
            status = 'deployed',
            deployed_at = GETDATE()
        WHERE model_id = @model_id;
        
        COMMIT TRANSACTION;
        
        PRINT '✅ Modelo ' + CAST(@model_id AS VARCHAR) + ' desplegado a producción';
    END TRY
    BEGIN CATCH
        ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

-- SP: Actualizar predicciones con valores reales
IF OBJECT_ID('ml.sp_update_predictions_with_actuals', 'P') IS NOT NULL
    DROP PROCEDURE ml.sp_update_predictions_with_actuals;
GO

CREATE PROCEDURE ml.sp_update_predictions_with_actuals
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Actualizar predicciones donde ya existe el valor real
    UPDATE p
    SET p.actual_close = ph.[close],
        p.actual_direction = CASE 
            WHEN ph.[close] > prev_ph.[close] THEN 'UP'
            WHEN ph.[close] < prev_ph.[close] THEN 'DOWN'
            ELSE 'NEUTRAL'
        END,
        p.absolute_error = ABS(p.predicted_close - ph.[close]),
        p.percentage_error = (p.predicted_close - ph.[close]) / ph.[close] * 100,
        p.direction_correct = CASE
            WHEN p.predicted_direction = CASE 
                WHEN ph.[close] > prev_ph.[close] THEN 'UP'
                WHEN ph.[close] < prev_ph.[close] THEN 'DOWN'
                ELSE 'NEUTRAL'
            END THEN 1
            ELSE 0
        END,
        p.updated_at = GETDATE()
    FROM ml.predictions p
    JOIN stage.precios_historicos ph ON p.ticker_id = ph.ticker_id AND p.target_date = ph.fecha
    JOIN stage.precios_historicos prev_ph ON p.ticker_id = prev_ph.ticker_id 
        AND prev_ph.fecha = DATEADD(day, -1, p.target_date)
    WHERE p.actual_close IS NULL
        AND p.target_date <= GETDATE();
    
    PRINT '✅ Predicciones actualizadas con valores reales';
END
GO

PRINT '✅ Schema ML creado exitosamente!';
PRINT '';
PRINT '📊 Tablas creadas:';
PRINT '   - ml.model_registry';
PRINT '   - ml.experiments';
PRINT '   - ml.experiment_generations';
PRINT '   - ml.predictions';
PRINT '   - ml.ab_tests';
PRINT '   - ml.feature_importance';
PRINT '';
PRINT '👁️  Vistas creadas:';
PRINT '   - ml.v_production_models';
PRINT '   - ml.v_prediction_performance';
PRINT '';
PRINT '⚙️  Procedimientos:';
PRINT '   - ml.sp_deploy_model';
PRINT '   - ml.sp_update_predictions_with_actuals';
GO
