"""
Databricks Utilities for Stock Market ETL
==========================================

Shared utilities for:
- Run ID generation and tracking
- Delta Lake operations
- Versioning and reproducibility
- Logging and monitoring

Author: Stock Market ETL Team
Date: 2025-12-24
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import subprocess
import os

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from delta.tables import DeltaTable


class RunManager:
    """Manages ETL runs and versioning in gold.runs table."""
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
        
    def create_run(
        self,
        run_type: str,
        features_version: str,
        data_ref: Optional[str] = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        notebook_path: Optional[str] = None
    ) -> str:
        """
        Create a new run record in gold.runs.
        
        Args:
            run_type: Type of run (train, predict, portfolio, backtest)
            features_version: Version of feature engineering logic
            data_ref: Delta version or timestamp reference
            model_name: Name of model (if applicable)
            model_version: MLflow model version URI
            params: Run parameters as dict
            constraints: Constraints applied as dict
            notebook_path: Path to notebook being executed
            
        Returns:
            run_id: Unique identifier for this run
        """
        run_id = str(uuid.uuid4())
        code_version = self._get_git_commit()
        
        # Get current username (Databricks)
        try:
            user_name = self.spark.sql("SELECT current_user()").first()[0]
        except:
            user_name = os.getenv("USER", "unknown")
        
        # Get cluster ID if available
        try:
            cluster_id = self.spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
        except:
            cluster_id = None
            
        # Get job ID if running in workflow
        try:
            job_id = self.spark.conf.get("spark.databricks.clusterUsageTags.jobId")
        except:
            job_id = None
        
        run_data = {
            "run_id": run_id,
            "run_type": run_type,
            "run_timestamp": datetime.now(timezone.utc),
            "user_name": user_name,
            "model_name": model_name,
            "model_version": model_version,
            "data_ref": data_ref or self._get_current_timestamp(),
            "features_version": features_version,
            "code_version": code_version,
            "params_json": json.dumps(params) if params else None,
            "constraints_json": json.dumps(constraints) if constraints else None,
            "status": "running",
            "metrics_json": None,
            "error_message": None,
            "execution_time_seconds": None,
            "databricks_job_id": job_id,
            "notebook_path": notebook_path,
            "cluster_id": cluster_id
        }
        
        # Insert into gold.runs
        df = self.spark.createDataFrame([run_data])
        df.write.format("delta").mode("append").saveAsTable("gold.runs")
        
        print(f"✓ Created run_id: {run_id}")
        print(f"  Type: {run_type}")
        print(f"  Features version: {features_version}")
        print(f"  Code version: {code_version}")
        
        return run_id
    
    def update_run_status(
        self,
        run_id: str,
        status: str,
        metrics: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None
    ):
        """Update run status and metrics."""
        
        updates = {
            "status": F.lit(status),
            "metrics_json": F.lit(json.dumps(metrics) if metrics else None),
            "error_message": F.lit(error_message)
        }
        
        if execution_time is not None:
            updates["execution_time_seconds"] = F.lit(execution_time)
        
        # Update using Delta merge
        delta_table = DeltaTable.forName(self.spark, "gold.runs")
        delta_table.update(
            condition=F.col("run_id") == run_id,
            set=updates
        )
        
        print(f"✓ Updated run {run_id}: status={status}")
    
    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as data reference."""
        return datetime.now(timezone.utc).isoformat()


class DeltaManager:
    """Manages Delta Lake operations with best practices."""
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
    
    def upsert(
        self,
        target_table: str,
        source_df: DataFrame,
        merge_keys: List[str],
        update_all: bool = True
    ):
        """
        Perform idempotent MERGE (upsert) into Delta table.
        
        Args:
            target_table: Name of target Delta table
            source_df: Source DataFrame to merge
            merge_keys: Columns to use for matching
            update_all: If True, update all columns on match
        """
        delta_table = DeltaTable.forName(self.spark, target_table)
        
        # Build merge condition
        merge_condition = " AND ".join([
            f"target.{key} = source.{key}" for key in merge_keys
        ])
        
        # Build update dict
        if update_all:
            update_dict = {col: f"source.{col}" for col in source_df.columns}
        else:
            # Only update non-key columns
            update_dict = {
                col: f"source.{col}" 
                for col in source_df.columns 
                if col not in merge_keys
            }
        
        # Execute merge
        (delta_table.alias("target")
            .merge(source_df.alias("source"), merge_condition)
            .whenMatchedUpdate(set=update_dict)
            .whenNotMatchedInsertAll()
            .execute())
        
        print(f"✓ Merged data into {target_table}")
    
    def get_table_version(self, table_name: str) -> int:
        """Get current Delta table version."""
        delta_table = DeltaTable.forName(self.spark, table_name)
        history = delta_table.history(1)
        return history.select("version").first()[0]
    
    def optimize_table(self, table_name: str, where: Optional[str] = None):
        """Run OPTIMIZE on Delta table."""
        optimize_sql = f"OPTIMIZE {table_name}"
        if where:
            optimize_sql += f" WHERE {where}"
        
        self.spark.sql(optimize_sql)
        print(f"✓ Optimized {table_name}")
    
    def vacuum_table(self, table_name: str, retention_hours: int = 168):
        """Run VACUUM on Delta table (default: 7 days retention)."""
        self.spark.sql(f"VACUUM {table_name} RETAIN {retention_hours} HOURS")
        print(f"✓ Vacuumed {table_name} (retention: {retention_hours}h)")


class ConfigManager:
    """Manages configuration loading."""
    
    @staticmethod
    def load_config(config_path: str = "/Workspace/Repos/stock-market/config/config.yaml") -> Dict[str, Any]:
        """Load YAML configuration file."""
        import yaml
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"⚠️  Config file not found: {config_path}")
            print("   Using default configuration")
            return {}
    
    @staticmethod
    def get_secret(scope: str, key: str, dbutils=None) -> Optional[str]:
        """Get secret from Databricks Secret Scope."""
        if dbutils is None:
            print("⚠️  dbutils not available, cannot retrieve secret")
            return None
        
        try:
            return dbutils.secrets.get(scope=scope, key=key)
        except Exception as e:
            print(f"⚠️  Failed to get secret {scope}/{key}: {e}")
            return None


def log_step(step_name: str, status: str = "START", details: Optional[str] = None):
    """Simple structured logging for pipeline steps."""
    timestamp = datetime.now(timezone.utc).isoformat()
    log_msg = f"[{timestamp}] [{status}] {step_name}"
    if details:
        log_msg += f" - {details}"
    print(log_msg)


def validate_dataframe(df: DataFrame, required_columns: List[str]) -> bool:
    """Validate DataFrame has required columns."""
    missing = set(required_columns) - set(df.columns)
    if missing:
        print(f"❌ Missing required columns: {missing}")
        return False
    return True


def add_audit_columns(df: DataFrame) -> DataFrame:
    """Add standard audit columns to DataFrame."""
    return df.withColumn("ingestion_timestamp", F.current_timestamp()) \
             .withColumn("last_updated", F.current_timestamp())
