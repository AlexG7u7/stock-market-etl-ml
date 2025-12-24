-- ============================================
-- DDL for Bronze Layer
-- ============================================
-- Purpose: Store raw API responses for audit and reprocessing
-- Author: Stock Market ETL Team
-- Date: 2025-12-24
-- ============================================

CREATE DATABASE IF NOT EXISTS bronze
COMMENT 'Bronze layer - Raw data from external sources'
LOCATION 'dbfs:/mnt/stock-market/bronze';

USE bronze;

-- Table: api_responses
-- Stores raw JSON responses from DataBursátil API
CREATE TABLE IF NOT EXISTS api_responses (
  response_id STRING NOT NULL COMMENT 'Unique identifier for this API response',
  endpoint STRING NOT NULL COMMENT 'API endpoint called (e.g., /v1/historical)',
  request_params MAP<STRING, STRING> COMMENT 'Request parameters as key-value pairs',
  response_body STRING COMMENT 'Raw JSON response body',
  response_status INT COMMENT 'HTTP status code',
  response_headers MAP<STRING, STRING> COMMENT 'Response headers',
  ingestion_timestamp TIMESTAMP NOT NULL COMMENT 'When this response was ingested',
  data_date DATE COMMENT 'Business date for the data (if applicable)',
  ticker STRING COMMENT 'Ticker symbol if request was for specific ticker',
  is_successful BOOLEAN COMMENT 'Whether the API call was successful',
  error_message STRING COMMENT 'Error message if call failed'
)
USING DELTA
PARTITIONED BY (data_date)
COMMENT 'Raw API responses from DataBursátil - enables full reprocessing and audit trail'
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.enableChangeDataFeed' = 'true'
);

-- Add constraints
ALTER TABLE api_responses 
ADD CONSTRAINT api_responses_pk PRIMARY KEY(response_id);

-- Optimize for common queries
OPTIMIZE api_responses;
ANALYZE TABLE api_responses COMPUTE STATISTICS;
