"""Módulo ETL para WALMEX"""
from .incremental import run as run_incremental
from .historical import run as run_historical

__all__ = ['run_incremental', 'run_historical']
