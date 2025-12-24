-- ============================================
-- DDL for Silver Layer
-- ============================================
-- Purpose: Clean, normalized data ready for analytics
-- Author: Stock Market ETL Team
-- Date: 2025-12-24
-- ============================================

CREATE DATABASE IF NOT EXISTS silver
COMMENT 'Silver layer - Cleaned and normalized data'
LOCATION 'dbfs:/mnt/stock-market/silver';

USE silver;

-- ============================================
-- Table: tickers
-- Master catalog of all tickers
-- ============================================
CREATE TABLE IF NOT EXISTS tickers (
  ticker STRING NOT NULL COMMENT 'Ticker symbol (e.g., AMXL, WALMEX)',
  ticker_name STRING COMMENT 'Full company name',
  market STRING COMMENT 'Market/Exchange (e.g., BMV, BIVA)',
  sector STRING COMMENT 'Industry sector',
  is_active BOOLEAN NOT NULL DEFAULT true COMMENT 'Whether ticker is currently active',
  added_date DATE NOT NULL COMMENT 'When ticker was added to catalog',
  deactivated_date DATE COMMENT 'When ticker was deactivated (if applicable)',
  metadata MAP<STRING, STRING> COMMENT 'Additional metadata (flexible schema)',
  last_updated TIMESTAMP NOT NULL COMMENT 'Last update timestamp'
)
USING DELTA
COMMENT 'Master catalog of tickers - ticker-agnostic design'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

ALTER TABLE tickers 
ADD CONSTRAINT tickers_pk PRIMARY KEY(ticker);

-- ============================================
-- Table: market_ohlcv
-- Historical market data in long format
-- ============================================
CREATE TABLE IF NOT EXISTS market_ohlcv (
  ticker STRING NOT NULL COMMENT 'Ticker symbol',
  date DATE NOT NULL COMMENT 'Trading date',
  open DOUBLE COMMENT 'Opening price',
  high DOUBLE COMMENT 'Highest price',
  low DOUBLE COMMENT 'Lowest price',
  close DOUBLE COMMENT 'Closing price',
  volume BIGINT COMMENT 'Trading volume',
  adjusted_close DOUBLE COMMENT 'Adjusted closing price (for splits/dividends)',
  currency STRING COMMENT 'Currency (e.g., MXN, USD)',
  source STRING COMMENT 'Data source (e.g., databursatil)',
  source_record_id STRING COMMENT 'Reference to source record in bronze',
  ingestion_timestamp TIMESTAMP NOT NULL COMMENT 'When record was ingested',
  last_updated TIMESTAMP NOT NULL COMMENT 'Last update timestamp'
)
USING DELTA
PARTITIONED BY (date)
COMMENT 'Historical OHLCV data in long format - supports any number of tickers'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

-- Logical primary key
ALTER TABLE market_ohlcv 
ADD CONSTRAINT market_ohlcv_pk PRIMARY KEY(ticker, date);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ticker ON market_ohlcv(ticker);
CREATE INDEX IF NOT EXISTS idx_date ON market_ohlcv(date);

-- Optimize
OPTIMIZE market_ohlcv;
ANALYZE TABLE market_ohlcv COMPUTE STATISTICS;
