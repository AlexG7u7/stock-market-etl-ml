"""
Módulo de conexión a SQL Server.
Maneja conexiones directas y vía SSH tunnel usando Cloudflare.
"""

import pyodbc
import subprocess
import time
from typing import Optional, Any
from contextlib import contextmanager
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLServerConnection:
    """
    Gestor de conexiones a SQL Server.
    Soporta conexión directa y vía SSH tunnel (Cloudflare).
    """
    
    def __init__(self, use_sqlalchemy: bool = False):
        """
        Inicializa el gestor de conexiones.
        
        Args:
            use_sqlalchemy: Si True, usa SQLAlchemy. Si False, usa pyodbc directo.
        """
        self.use_sqlalchemy = use_sqlalchemy
        self.connection = None
        self.engine = None
        self.ssh_process = None
        
        # Iniciar SSH tunnel si está habilitado
        if Config.SSH_ENABLED:
            self._start_ssh_tunnel()
    
    def _start_ssh_tunnel(self):
        """Inicia túnel SSH usando Cloudflare Access."""
        try:
            logger.info("🔐 Iniciando túnel SSH con Cloudflare...")
            
            # Comando para establecer túnel SSH
            # cloudflared access ssh --hostname ssh.rod-b-op.com --user rodri
            cmd = [
                "cloudflared",
                "access",
                "ssh",
                "--hostname", Config.SSH_HOSTNAME,
                "--user", Config.SSH_USER
            ]
            
            logger.debug(f"Comando SSH: {' '.join(cmd)}")
            
            # Nota: El túnel Cloudflare funciona de manera diferente
            # No necesita process background, se usa directamente en la conexión
            logger.info("✅ Túnel SSH configurado (Cloudflare Access)")
            
        except Exception as e:
            logger.error(f"❌ Error configurando túnel SSH: {e}")
            raise
    
    def _get_connection_string(self) -> str:
        """Genera connection string para pyodbc."""
        return Config.get_connection_string()
    
    def connect(self):
        """Establece conexión con SQL Server."""
        try:
            if self.use_sqlalchemy:
                self._connect_sqlalchemy()
            else:
                self._connect_pyodbc()
            
            logger.info("✅ Conexión establecida con SQL Server")
            return self.connection if not self.use_sqlalchemy else self.engine
            
        except Exception as e:
            logger.error(f"❌ Error conectando a SQL Server: {e}")
            raise
    
    def _connect_pyodbc(self):
        """Conexión usando pyodbc."""
        conn_str = self._get_connection_string()
        self.connection = pyodbc.connect(conn_str)
        logger.debug(f"Conectado via pyodbc a {Config.SQL_SERVER_DATABASE}")
    
    def _connect_sqlalchemy(self):
        """Conexión usando SQLAlchemy."""
        url = Config.get_sqlalchemy_url()
        self.engine = create_engine(
            url,
            poolclass=NullPool,  # No usar pool para evitar problemas con túnel SSH
            echo=Config.DEBUG
        )
        self.connection = self.engine.connect()
        logger.debug(f"Conectado via SQLAlchemy a {Config.SQL_SERVER_DATABASE}")
    
    def close(self):
        """Cierra la conexión."""
        try:
            if self.connection:
                self.connection.close()
                logger.info("🔒 Conexión cerrada")
            
            if self.ssh_process:
                self.ssh_process.terminate()
                logger.info("🔒 Túnel SSH cerrado")
                
        except Exception as e:
            logger.error(f"Error cerrando conexión: {e}")
    
    def __enter__(self):
        """Context manager: entrada."""
        self.connect()
        return self.connection if not self.use_sqlalchemy else self.engine
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: salida."""
        self.close()
    
    def execute_query(self, query: str, params: tuple = None) -> Any:
        """
        Ejecuta una query SQL.
        
        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (opcional)
            
        Returns:
            Resultado de la query
        """
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                cursor.close()
                return results
            else:
                self.connection.commit()
                cursor.close()
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"Error ejecutando query: {e}")
            logger.debug(f"Query: {query[:200]}...")
            raise
    
    def execute_stored_procedure(self, sp_name: str, params: tuple = None):
        """
        Ejecuta un stored procedure.
        
        Args:
            sp_name: Nombre del stored procedure
            params: Parámetros del SP
            
        Returns:
            Resultados del SP
        """
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(f"EXEC {sp_name} {','.join(['?'] * len(params))}", params)
            else:
                cursor.execute(f"EXEC {sp_name}")
            
            results = cursor.fetchall()
            cursor.close()
            return results
            
        except Exception as e:
            logger.error(f"Error ejecutando SP '{sp_name}': {e}")
            raise
    
    def read_sql(self, query: str, params: dict = None) -> pd.DataFrame:
        """
        Lee datos SQL directamente a DataFrame.
        
        Args:
            query: Query SQL
            params: Parámetros (opcional)
            
        Returns:
            DataFrame con resultados
        """
        if not self.connection:
            self.connect()
        
        try:
            if self.use_sqlalchemy:
                df = pd.read_sql(query, self.engine, params=params)
            else:
                df = pd.read_sql(query, self.connection, params=params)
            
            logger.debug(f"Leídas {len(df)} filas desde SQL Server")
            return df
            
        except Exception as e:
            logger.error(f"Error leyendo SQL: {e}")
            raise
    
    def insert_dataframe(self, df: pd.DataFrame, table_name: str, 
                        if_exists: str = 'append', chunksize: int = 1000):
        """
        Inserta DataFrame en SQL Server.
        
        Args:
            df: DataFrame a insertar
            table_name: Nombre de la tabla
            if_exists: 'append', 'replace', 'fail'
            chunksize: Tamaño de lote para inserción
        """
        if df.empty:
            logger.warning(f"DataFrame vacío, no se insertará nada en '{table_name}'")
            return 0
        
        try:
            # SQLAlchemy es mejor para bulk inserts
            if not self.use_sqlalchemy:
                logger.warning("Recomendado usar SQLAlchemy para bulk inserts")
                temp_engine = create_engine(Config.get_sqlalchemy_url(), poolclass=NullPool)
            else:
                temp_engine = self.engine
            
            df.to_sql(
                name=table_name,
                con=temp_engine,
                if_exists=if_exists,
                index=False,
                chunksize=chunksize,
                method='multi'
            )
            
            logger.info(f"✅ Insertadas {len(df)} filas en tabla '{table_name}'")
            return len(df)
            
        except Exception as e:
            logger.error(f"❌ Error insertando DataFrame en '{table_name}': {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión a SQL Server.
        
        Returns:
            True si la conexión es exitosa
        """
        try:
            if not self.connection:
                self.connect()
            
            query = "SELECT @@VERSION AS version, DB_NAME() AS database_name"
            result = self.execute_query(query)
            
            if result:
                version = result[0][0]
                db_name = result[0][1]
                logger.info(f"✅ Conexión exitosa a base de datos: {db_name}")
                logger.debug(f"SQL Server Version: {version[:100]}...")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Test de conexión falló: {e}")
            return False


@contextmanager
def get_connection(use_sqlalchemy: bool = False):
    """
    Context manager para obtener conexión a SQL Server.
    
    Args:
        use_sqlalchemy: Si usar SQLAlchemy engine
        
    Yields:
        Conexión activa
        
    Example:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emisoras")
    """
    conn_manager = SQLServerConnection(use_sqlalchemy=use_sqlalchemy)
    try:
        connection = conn_manager.connect()
        yield connection
    finally:
        conn_manager.close()


if __name__ == "__main__":
    # Testing de conexión
    print("=" * 70)
    print("TEST DE CONEXIÓN SQL SERVER")
    print("=" * 70)
    
    # Validar configuración primero
    if not Config.validate():
        print("\n❌ Configuración inválida. Verifica tu archivo .env")
        exit(1)
    
    # Test 1: Conexión pyodbc
    print("\n📡 Test 1: Conexión con pyodbc...")
    try:
        with get_connection(use_sqlalchemy=False) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DB_NAME() AS db")
            result = cursor.fetchone()
            print(f"✅ Base de datos: {result[0]}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Conexión SQLAlchemy
    print("\n📡 Test 2: Conexión con SQLAlchemy...")
    try:
        conn_manager = SQLServerConnection(use_sqlalchemy=True)
        if conn_manager.test_connection():
            print("✅ Test de conexión exitoso")
            
            # Listar tablas
            query = """
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """
            df = conn_manager.read_sql(query)
            print(f"\n📊 Tablas en base de datos ({len(df)}):")
            for idx, row in df.iterrows():
                print(f"  - {row['TABLE_NAME']}")
        
        conn_manager.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "=" * 70)
