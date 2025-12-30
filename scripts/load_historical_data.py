"""
Script para cargar datos históricos desde Yahoo Finance
"""
import yfinance as yf
import pyodbc
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from loguru import logger

# Cargar variables de entorno
load_dotenv()

def get_connection():
    """Crear conexión a SQL Server"""
    server = os.getenv('SQL_SERVER', 'localhost')
    database = os.getenv('SQL_DATABASE', 'MercadoBursatil')
    username = os.getenv('SQL_USER', '')
    password = os.getenv('SQL_PASSWORD', '')
    
    if username and password:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password}"
        )
    else:
        # Autenticación de Windows
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
        )
    
    return pyodbc.connect(conn_str)

def get_ticker_id(conn, ticker_symbol):
    """Obtener ticker_id de cat_tickers"""
    cursor = conn.cursor()
    query = "SELECT ticker_id FROM stage.cat_tickers WHERE emisora_serie = ?"
    cursor.execute(query, ticker_symbol)
    row = cursor.fetchone()
    cursor.close()
    
    if row:
        return row[0]
    else:
        raise ValueError(f"Ticker {ticker_symbol} no encontrado en cat_tickers")

def download_historical_data(yahoo_ticker, start_date, end_date):
    """Descargar datos de Yahoo Finance"""
    logger.info(f"📥 Descargando datos de {yahoo_ticker} desde {start_date} hasta {end_date}")
    
    ticker = yf.Ticker(yahoo_ticker)
    df = ticker.history(start=start_date, end=end_date)
    
    if df.empty:
        raise ValueError(f"No se encontraron datos para {yahoo_ticker}")
    
    # Renombrar columnas al formato de nuestra base de datos
    df = df.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    
    # Resetear índice para tener fecha como columna
    df = df.reset_index()
    df = df.rename(columns={'Date': 'fecha'})
    
    # Seleccionar solo las columnas que necesitamos
    df = df[['fecha', 'open', 'high', 'low', 'close', 'volume']]
    
    logger.success(f"✅ Descargados {len(df)} registros")
    logger.info(f"   Rango: {df['fecha'].min()} a {df['fecha'].max()}")
    
    return df

def insert_historical_data(conn, ticker_id, df):
    """Insertar datos en stage.precios_historicos"""
    cursor = conn.cursor()
    
    # Query de inserción (MERGE para evitar duplicados)
    merge_query = """
    MERGE INTO stage.precios_historicos AS target
    USING (SELECT ? AS ticker_id, ? AS fecha, ? AS [open], ? AS [high], 
                  ? AS [low], ? AS [close], ? AS volume) AS source
    ON target.ticker_id = source.ticker_id AND target.fecha = source.fecha
    WHEN MATCHED THEN
        UPDATE SET 
            [open] = source.[open],
            [high] = source.[high],
            [low] = source.[low],
            [close] = source.[close],
            volume = source.volume
    WHEN NOT MATCHED THEN
        INSERT (ticker_id, fecha, [open], [high], [low], [close], volume)
        VALUES (source.ticker_id, source.fecha, source.[open], source.[high], 
                source.[low], source.[close], source.volume);
    """
    
    inserted = 0
    updated = 0
    
    logger.info(f"💾 Insertando {len(df)} registros en la base de datos...")
    
    for idx, row in df.iterrows():
        cursor.execute(
            merge_query,
            ticker_id,
            row['fecha'],
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
            int(row['volume'])
        )
        
        if (idx + 1) % 100 == 0:
            logger.info(f"   Procesados {idx + 1}/{len(df)} registros...")
    
    conn.commit()
    cursor.close()
    
    logger.success(f"✅ Datos insertados correctamente")

def main():
    """Función principal"""
    # Configuración
    TICKERS = [
        {'emisora_serie': 'WALMEX*', 'yahoo': 'WALMEX.MX'},
        {'emisora_serie': 'ALSEA*', 'yahoo': 'ALSEA.MX'},
    ]
    
    # Obtener últimos 5 años de datos
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 5)  # 5 años
    
    logger.info("=" * 80)
    logger.info("📊 CARGA DE DATOS HISTÓRICOS - Yahoo Finance")
    logger.info("=" * 80)
    logger.info(f"Período: {start_date.date()} a {end_date.date()}")
    logger.info("")
    
    # Conectar a base de datos
    logger.info("🔗 Conectando a SQL Server...")
    conn = get_connection()
    logger.success("✅ Conexión establecida")
    logger.info("")
    
    try:
        for ticker_config in TICKERS:
            emisora_serie = ticker_config['emisora_serie']
            yahoo_ticker = ticker_config['yahoo']
            
            logger.info(f"📈 Procesando {emisora_serie} ({yahoo_ticker})")
            logger.info("-" * 80)
            
            try:
                # Obtener ticker_id
                ticker_id = get_ticker_id(conn, emisora_serie)
                logger.info(f"✅ ticker_id: {ticker_id}")
                
                # Descargar datos
                df = download_historical_data(
                    yahoo_ticker,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )
                
                # Insertar en base de datos
                insert_historical_data(conn, ticker_id, df)
                
                logger.info("")
                
            except Exception as e:
                logger.error(f"❌ Error procesando {emisora_serie}: {str(e)}")
                logger.info("")
                continue
        
        logger.info("=" * 80)
        logger.success("✅ CARGA COMPLETADA")
        logger.info("=" * 80)
        
    finally:
        conn.close()
        logger.info("🔌 Conexión cerrada")

if __name__ == "__main__":
    main()
