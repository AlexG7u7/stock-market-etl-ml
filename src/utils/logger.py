"""
Sistema de logging centralizado para el proyecto ETL.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

from src.utils.config import Config


class ETLLogger:
    """Logger personalizado para el proyecto ETL."""
    
    _loggers = {}
    
    @classmethod
    def get_logger(cls, name: str = "etl", log_file: Optional[str] = None) -> logging.Logger:
        """
        Obtiene o crea un logger configurado.
        
        Args:
            name: Nombre del logger
            log_file: Nombre del archivo de log (opcional)
            
        Returns:
            Logger configurado
        """
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Evitar duplicación de handlers
        if logger.handlers:
            return logger
        
        # Formato de logs
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Handler para archivo
        if log_file is None:
            log_file = Config.LOG_FILE
        else:
            log_file = Config.LOGS_DIR / log_file
        
        # Crear directorio si no existe
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=Config.LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        cls._loggers[name] = logger
        return logger
    
    @classmethod
    def log_etl_start(cls, etl_type: str, logger: Optional[logging.Logger] = None):
        """Log inicio de proceso ETL."""
        if logger is None:
            logger = cls.get_logger()
        
        separator = "=" * 70
        logger.info(separator)
        logger.info(f"INICIO ETL: {etl_type.upper()}")
        logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(separator)
    
    @classmethod
    def log_etl_end(cls, etl_type: str, stats: dict, logger: Optional[logging.Logger] = None):
        """Log fin de proceso ETL con estadísticas."""
        if logger is None:
            logger = cls.get_logger()
        
        separator = "=" * 70
        logger.info(separator)
        logger.info(f"FIN ETL: {etl_type.upper()}")
        logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if stats:
            logger.info("Estadísticas:")
            for key, value in stats.items():
                logger.info(f"  - {key}: {value}")
        
        logger.info(separator)
    
    @classmethod
    def log_api_call(cls, endpoint: str, params: dict, logger: Optional[logging.Logger] = None):
        """Log llamada a API."""
        if logger is None:
            logger = cls.get_logger()
        
        logger.debug(f"API Call: {endpoint}")
        logger.debug(f"Params: {params}")
    
    @classmethod
    def log_db_operation(cls, operation: str, table: str, rows: int, logger: Optional[logging.Logger] = None):
        """Log operación de base de datos."""
        if logger is None:
            logger = cls.get_logger()
        
        logger.info(f"DB {operation}: {rows} filas en tabla '{table}'")
    
    @classmethod
    def log_error(cls, error: Exception, context: str = "", logger: Optional[logging.Logger] = None):
        """Log error con contexto."""
        if logger is None:
            logger = cls.get_logger()
        
        logger.error(f"ERROR{' - ' + context if context else ''}: {str(error)}", exc_info=True)


def get_logger(name: str = "etl") -> logging.Logger:
    """
    Función helper para obtener logger.
    
    Args:
        name: Nombre del logger
        
    Returns:
        Logger configurado
    """
    return ETLLogger.get_logger(name)


if __name__ == "__main__":
    # Testing
    logger = get_logger("test")
    
    logger.debug("Este es un mensaje DEBUG")
    logger.info("Este es un mensaje INFO")
    logger.warning("Este es un mensaje WARNING")
    logger.error("Este es un mensaje ERROR")
    
    # Simular ETL
    ETLLogger.log_etl_start("historico", logger)
    logger.info("Procesando datos...")
    ETLLogger.log_api_call("/v2/historicos", {"emisora": "WALMEX*"}, logger)
    ETLLogger.log_db_operation("INSERT", "precios_historicos", 250, logger)
    
    stats = {
        "registros_procesados": 250,
        "registros_insertados": 245,
        "errores": 5,
        "duración": "15.3s"
    }
    ETLLogger.log_etl_end("historico", stats, logger)
    
    print(f"\n✅ Log guardado en: {Config.LOG_FILE}")
