"""
Módulo de configuración centralizada.
Carga variables de entorno y archivos de configuración.
"""

import os
from pathlib import Path
from typing import Any, Dict
import yaml
from dotenv import load_dotenv

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Cargar variables de entorno
env_path = CONFIG_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠️  Warning: {env_path} no encontrado. Usando .env.example como referencia.")


class Config:
    """Configuración centralizada del proyecto."""
    
    # Directorios
    BASE_DIR = BASE_DIR
    CONFIG_DIR = CONFIG_DIR
    DATA_DIR = DATA_DIR
    LOGS_DIR = LOGS_DIR
    
    # API DataBursatil
    DATABURSATIL_API_TOKEN = os.getenv("DATABURSATIL_API_TOKEN", "")
    DATABURSATIL_BASE_URL = os.getenv("DATABURSATIL_BASE_URL", "https://api.databursatil.com/v2")
    
    # SQL Server
    SQL_SERVER_HOST = os.getenv("SQL_SERVER", os.getenv("SQL_SERVER_HOST", "localhost"))
    SQL_SERVER_PORT = int(os.getenv("SQL_SERVER_PORT", "1433"))
    SQL_SERVER_DATABASE = os.getenv("SQL_DATABASE", os.getenv("SQL_SERVER_DATABASE", "MercadoBursatil"))
    SQL_SERVER_USER = os.getenv("SQL_USER", os.getenv("SQL_SERVER_USER", "sa"))
    SQL_SERVER_PASSWORD = os.getenv("SQL_PASSWORD", os.getenv("SQL_SERVER_PASSWORD", ""))
    SQL_SERVER_DRIVER = os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    
    # SSH Tunnel
    SSH_ENABLED = os.getenv("SSH_ENABLED", "false").lower() == "true"
    SSH_HOSTNAME = os.getenv("SSH_HOSTNAME", "ssh.rod-b-op.com")
    SSH_USER = os.getenv("SSH_USER", "rodri")
    SSH_LOCAL_PORT = int(os.getenv("SSH_LOCAL_PORT", "1433"))
    SSH_REMOTE_PORT = int(os.getenv("SSH_REMOTE_PORT", "1433"))
    CLOUDFLARE_TUNNEL_ID = os.getenv("CLOUDFLARE_TUNNEL_ID", "")
    
    # ETL Configuration
    ETL_BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "50"))
    ETL_MAX_RETRIES = int(os.getenv("ETL_MAX_RETRIES", "3"))
    ETL_RETRY_DELAY = int(os.getenv("ETL_RETRY_DELAY", "5"))
    ETL_TIMEOUT = int(os.getenv("ETL_TIMEOUT", "30"))
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = LOGS_DIR / os.getenv("LOG_FILE", "etl.log")
    LOG_MAX_SIZE_MB = int(os.getenv("LOG_MAX_SIZE_MB", "10"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # Environment
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    
    @classmethod
    def get_connection_string(cls) -> str:
        """Genera connection string para SQL Server."""
        return (
            f"DRIVER={{{cls.SQL_SERVER_DRIVER}}};"
            f"SERVER={cls.SQL_SERVER_HOST},{cls.SQL_SERVER_PORT};"
            f"DATABASE={cls.SQL_SERVER_DATABASE};"
            f"UID={cls.SQL_SERVER_USER};"
            f"PWD={cls.SQL_SERVER_PASSWORD};"
            f"TrustServerCertificate=yes;"
        )
    
    @classmethod
    def get_sqlalchemy_url(cls) -> str:
        """Genera URL para SQLAlchemy."""
        from urllib.parse import quote_plus
        
        conn_str = cls.get_connection_string()
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"
    
    @classmethod
    def validate(cls) -> bool:
        """Valida que las configuraciones críticas estén presentes."""
        errors = []
        
        if not cls.DATABURSATIL_API_TOKEN:
            errors.append("DATABURSATIL_API_TOKEN no configurado")
        
        if not cls.SQL_SERVER_PASSWORD:
            errors.append("SQL_SERVER_PASSWORD no configurado")
        
        if cls.SSH_ENABLED and not cls.CLOUDFLARE_TUNNEL_ID:
            errors.append("SSH habilitado pero CLOUDFLARE_TUNNEL_ID no configurado")
        
        if errors:
            print("❌ Errores de configuración:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        print("✅ Configuración validada correctamente")
        return True
    
    @classmethod
    def load_yaml_config(cls, filename: str = "config.yaml") -> Dict[str, Any]:
        """Carga configuración desde archivo YAML."""
        config_path = cls.CONFIG_DIR / filename
        
        if not config_path.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @classmethod
    def get_tickers(cls, group: str = "ipc_components") -> list:
        """Obtiene lista de tickers desde config.yaml."""
        try:
            config = cls.load_yaml_config()
            return config.get("tickers", {}).get(group, [])
        except Exception as e:
            print(f"⚠️  Error cargando tickers: {e}")
            return []


# Crear directorios si no existen
def ensure_directories():
    """Asegura que existan los directorios necesarios."""
    directories = [
        Config.DATA_DIR / "raw",
        Config.DATA_DIR / "processed",
        Config.DATA_DIR / "backups",
        Config.LOGS_DIR,
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# Ejecutar al importar
ensure_directories()


if __name__ == "__main__":
    # Testing
    print("=" * 50)
    print("CONFIGURACIÓN DEL PROYECTO")
    print("=" * 50)
    print(f"Base Dir: {Config.BASE_DIR}")
    print(f"API URL: {Config.DATABURSATIL_BASE_URL}")
    print(f"API Token: {'✅ Configurado' if Config.DATABURSATIL_API_TOKEN else '❌ No configurado'}")
    print(f"SQL Server: {Config.SQL_SERVER_HOST}:{Config.SQL_SERVER_PORT}")
    print(f"Database: {Config.SQL_SERVER_DATABASE}")
    print(f"SSH Enabled: {Config.SSH_ENABLED}")
    print(f"Environment: {Config.ENVIRONMENT}")
    print(f"Debug: {Config.DEBUG}")
    print("=" * 50)
    
    # Validar configuración
    Config.validate()
    
    # Mostrar tickers
    print(f"\nTickers IPC: {len(Config.get_tickers('ipc_components'))} emisoras")
    print(Config.get_tickers('ipc_components')[:5], "...")
