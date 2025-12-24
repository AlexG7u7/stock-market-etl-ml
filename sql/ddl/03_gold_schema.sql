-- ============================================
-- DDL for Gold Layer
-- ============================================
-- Purpose: Business-level aggregates, features, predictions, and portfolios
-- Author: Stock Market ETL Team
-- Date: 2025-12-24
-- ============================================

CREATE DATABASE IF NOT EXISTS gold
COMMENT 'Gold layer - Business-level aggregates and ML artifacts'
LOCATION 'dbfs:/mnt/stock-market/gold';

USE gold;

-- ============================================
-- Table: runs
-- Central versioning and reproducibility table
-- ============================================
CREATE TABLE IF NOT EXISTS runs (
  run_id STRING NOT NULL COMMENT 'Unique identifier for this run (UUID)',
  run_type STRING NOT NULL COMMENT 'Type: train, predict, portfolio, backtest',
  run_timestamp TIMESTAMP NOT NULL COMMENT 'When run was executed',
  user_name STRING COMMENT 'User who triggered the run',
  
  -- Versioning fields
  model_name STRING COMMENT 'Model name (if applicable)',
  model_version STRING COMMENT 'MLflow model version URI',
  data_ref STRING NOT NULL COMMENT 'Delta table version or timestamp used',
  features_version STRING NOT NULL COMMENT 'Version of feature engineering logic',
  code_version STRING COMMENT 'Git commit SHA',
  
  -- Configuration
  params_json STRING COMMENT 'Run parameters as JSON (includes backtest oracle flag)',
  constraints_json STRING COMMENT 'Constraints applied (e.g., portfolio constraints)',
  
  -- Results
  status STRING NOT NULL COMMENT 'Status: running, completed, failed',
  metrics_json STRING COMMENT 'Output metrics as JSON',
  error_message STRING COMMENT 'Error details if failed',
  
  -- Metadata
  execution_time_seconds DOUBLE COMMENT 'Total execution time',
  databricks_job_id STRING COMMENT 'Databricks job ID if run via workflow',
  notebook_path STRING COMMENT 'Path to notebook executed',
  cluster_id STRING COMMENT 'Cluster ID where run executed'
)
USING DELTA
COMMENT 'Central table for versioning and reproducibility - every run is tracked here'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

ALTER TABLE runs 
ADD CONSTRAINT runs_pk PRIMARY KEY(run_id);

-- ============================================
-- Table: features_daily
-- Calculated features for ML models
-- ============================================
CREATE TABLE IF NOT EXISTS features_daily (
  ticker STRING NOT NULL COMMENT 'Ticker symbol',
  date DATE NOT NULL COMMENT 'Feature date',
  features_version STRING NOT NULL COMMENT 'Version of feature engineering logic',
  
  -- Core features (extensible design)
  features MAP<STRING, DOUBLE> COMMENT 'Feature name -> value mapping (flexible schema)',
  
  -- Alternative: JSON string for complex nested features
  -- features_json STRING COMMENT 'All features as JSON',
  
  -- Metadata
  created_timestamp TIMESTAMP NOT NULL COMMENT 'When features were created',
  run_id STRING COMMENT 'Reference to gold.runs'
)
USING DELTA
PARTITIONED BY (date)
COMMENT 'Daily features for ML - versioned and ticker-agnostic'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

ALTER TABLE features_daily 
ADD CONSTRAINT features_daily_pk PRIMARY KEY(ticker, date, features_version);

-- ============================================
-- Table: predictions
-- Model predictions
-- ============================================
CREATE TABLE IF NOT EXISTS predictions (
  prediction_id STRING NOT NULL COMMENT 'Unique prediction identifier',
  run_id STRING NOT NULL COMMENT 'Reference to gold.runs',
  ticker STRING NOT NULL COMMENT 'Ticker symbol',
  prediction_date DATE NOT NULL COMMENT 'Date prediction was made',
  target_date DATE NOT NULL COMMENT 'Date being predicted',
  
  -- Predictions
  predicted_return DOUBLE COMMENT 'Predicted return',
  predicted_direction INT COMMENT 'Predicted direction: 1 (up), -1 (down), 0 (neutral)',
  confidence DOUBLE COMMENT 'Prediction confidence [0-1]',
  
  -- Model details
  model_name STRING COMMENT 'Model used',
  model_version STRING COMMENT 'MLflow model version',
  
  -- Optional: multiple predictions
  predictions_json STRING COMMENT 'Additional predictions as JSON',
  
  created_timestamp TIMESTAMP NOT NULL COMMENT 'When prediction was created'
)
USING DELTA
PARTITIONED BY (target_date)
COMMENT 'Model predictions - linked to runs for reproducibility'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

ALTER TABLE predictions 
ADD CONSTRAINT predictions_pk PRIMARY KEY(prediction_id);

-- ============================================
-- Table: portfolio_holdings
-- Optimized portfolios
-- ============================================
CREATE TABLE IF NOT EXISTS portfolio_holdings (
  portfolio_id STRING NOT NULL COMMENT 'Unique portfolio identifier',
  run_id STRING NOT NULL COMMENT 'Reference to gold.runs (type=portfolio)',
  ticker STRING NOT NULL COMMENT 'Ticker symbol',
  portfolio_date DATE NOT NULL COMMENT 'Date portfolio was created',
  rebalance_date DATE NOT NULL COMMENT 'Date portfolio should be rebalanced',
  
  -- Holdings
  weight DOUBLE NOT NULL COMMENT 'Portfolio weight [0-1]',
  shares BIGINT COMMENT 'Number of shares (if calculated)',
  
  -- Portfolio metrics (duplicated for convenience)
  expected_return DOUBLE COMMENT 'Expected portfolio return',
  expected_volatility DOUBLE COMMENT 'Expected portfolio volatility',
  sharpe_ratio DOUBLE COMMENT 'Expected Sharpe ratio',
  
  -- Metadata
  optimizer_type STRING COMMENT 'Optimizer used (e.g., mean_variance, risk_parity)',
  constraints_json STRING COMMENT 'Constraints applied as JSON',
  created_timestamp TIMESTAMP NOT NULL COMMENT 'When portfolio was created'
)
USING DELTA
PARTITIONED BY (portfolio_date)
COMMENT 'Optimized portfolio holdings - versioned and reproducible'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

ALTER TABLE portfolio_holdings 
ADD CONSTRAINT portfolio_holdings_pk PRIMARY KEY(portfolio_id, ticker);

-- ============================================
-- Optimize all tables
-- ============================================
OPTIMIZE runs;
OPTIMIZE features_daily;
OPTIMIZE predictions;
OPTIMIZE portfolio_holdings;

-- ============================================
-- Compute statistics for query optimization
-- ============================================
ANALYZE TABLE runs COMPUTE STATISTICS;
ANALYZE TABLE features_daily COMPUTE STATISTICS;
ANALYZE TABLE predictions COMPUTE STATISTICS;
ANALYZE TABLE portfolio_holdings COMPUTE STATISTICS;
