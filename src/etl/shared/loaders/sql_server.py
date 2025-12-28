"""
Loader para SQL Server
Maneja la carga de datos a stage.precios_historicos con lógica UPSERT
"""
import pyodbc
from typing import List, Optional
from loguru import logger

from ..models.precio import PrecioHistorico


class SQLServerLoader:
    """
    Loader genérico para cargar precios históricos a SQL Server
    Implementa lógica UPSERT (UPDATE si existe, INSERT si no)
    """
    
    def __init__(
        self,
        server: str,
        database: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = "ODBC Driver 17 for SQL Server"
    ):
        """
        Inicializa el loader
        
        Args:
            server: Servidor SQL Server
            database: Nombre de la base de datos
            username: Usuario (opcional si usa Windows Auth)
            password: Contraseña
            driver: Driver ODBC
        """
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver
        self._connection = None
    
    def connect(self):
        """Establece conexión a SQL Server"""
        if self._connection is not None:
            logger.debug("Conexión ya establecida")
            return
        
        try:
            if self.username and self.password:
                # SQL Server Authentication
                conn_str = (
                    f"DRIVER={{{self.driver}}};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password}"
                )
            else:
                # Windows Authentication
                conn_str = (
                    f"DRIVER={{{self.driver}}};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"Trusted_Connection=yes;"
                )
            
            self._connection = pyodbc.connect(conn_str)
            logger.success(f"Conectado a SQL Server: {self.server}/{self.database}")
            
        except Exception as e:
            logger.error(f"Error conectando a SQL Server: {str(e)}")
            raise
    
    def disconnect(self):
        """Cierra la conexión"""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Conexión a SQL Server cerrada")
    
    def load(self, precios: List[PrecioHistorico], batch_size: int = 100) -> dict:
        """
        Carga precios a la base de datos con lógica UPSERT
        
        Args:
            precios: Lista de PrecioHistorico a cargar
            batch_size: Tamaño del batch para commits
            
        Returns:
            Diccionario con estadísticas: {inserted, updated, errors}
        """
        if not precios:
            logger.warning("No hay precios para cargar")
            return {'inserted': 0, 'updated': 0, 'errors': 0}
        
        self.connect()
        
        stats = {'inserted': 0, 'updated': 0, 'errors': 0}
        cursor = self._connection.cursor()
        
        try:
            for i, precio in enumerate(precios, 1):
                try:
                    # Verificar si existe
                    cursor.execute(
                        """
                        SELECT precio_id 
                        FROM stage.precios_historicos 
                        WHERE ticker_id = ? AND fecha = ?
                        """,
                        (precio.ticker_id, precio.fecha)
                    )
                    
                    existe = cursor.fetchone()
                    
                    if existe:
                        # UPDATE
                        cursor.execute(
                            """
                            UPDATE stage.precios_historicos
                            SET [open] = ?,
                                [high] = ?,
                                [low] = ?,
                                [close] = ?,
                                volume = ?,
                                importe = ?
                            WHERE ticker_id = ? AND fecha = ?
                            """,
                            (
                                precio.open, precio.high, precio.low, precio.close,
                                precio.volume, precio.importe,
                                precio.ticker_id, precio.fecha
                            )
                        )
                        stats['updated'] += 1
                        logger.debug(f"Actualizado: {precio.fecha}")
                    else:
                        # INSERT
                        cursor.execute(
                            """
                            INSERT INTO stage.precios_historicos 
                            (ticker_id, fecha, [open], [high], [low], [close], volume, importe)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                precio.ticker_id, precio.fecha,
                                precio.open, precio.high, precio.low, precio.close,
                                precio.volume, precio.importe
                            )
                        )
                        stats['inserted'] += 1
                        logger.debug(f"Insertado: {precio.fecha}")
                    
                    # Commit cada batch_size registros
                    if i % batch_size == 0:
                        self._connection.commit()
                        logger.info(f"Procesados {i}/{len(precios)} registros")
                
                except Exception as e:
                    logger.error(f"Error procesando registro {precio.fecha}: {str(e)}")
                    stats['errors'] += 1
            
            # Commit final
            self._connection.commit()
            
            logger.success(
                f"Carga completada - Insertados: {stats['inserted']}, "
                f"Actualizados: {stats['updated']}, Errores: {stats['errors']}"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error en carga masiva: {str(e)}")
            self._connection.rollback()
            raise
        
        finally:
            cursor.close()
    
    def __enter__(self):
        """Context manager enter"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
