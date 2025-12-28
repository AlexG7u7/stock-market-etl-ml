#!/usr/bin/env python3
"""
Script para verificar y agregar tickers a stage.cat_tickers
Debe ejecutarse ANTES de los ETL históricos
"""
import os
import sys
import pyodbc
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Tickers a verificar/agregar
TICKERS_A_VERIFICAR = [
    {
        'emisora_serie': 'WALMEX*',
        'emisora': 'WALMEX',
        'serie': '*',
        'nombre': 'Wal-Mart de México',
        'bolsa': 'BMV',
        'mercado': 'CAPITAL',
        'isin': 'MXP801141016'
    },
    {
        'emisora_serie': 'ALSEA*',
        'emisora': 'ALSEA',
        'serie': '*',
        'nombre': 'Alsea',
        'bolsa': 'BMV',
        'mercado': 'CAPITAL',
        'isin': 'MXP001311150'
    },
    {
        'emisora_serie': 'ALFAA',
        'emisora': 'ALFA',
        'serie': 'A',
        'nombre': 'Alfa',
        'bolsa': 'BMV',
        'mercado': 'CAPITAL',
        'isin': 'MXP001391012'
    }
]


def conectar_bd():
    """Conecta a SQL Server"""
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={os.getenv('SQL_SERVER')};"
            f"DATABASE={os.getenv('SQL_DATABASE')};"
            f"UID={os.getenv('SQL_USER')};"
            f"PWD={os.getenv('SQL_PASSWORD')}"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {str(e)}")
        sys.exit(1)


def verificar_ticker(cursor, emisora, serie):
    """Verifica si un ticker existe en stage.cat_tickers"""
    cursor.execute(
        "SELECT ticker_id, emisora, serie, nombre FROM stage.cat_tickers WHERE emisora = ? AND serie = ?",
        (emisora, serie)
    )
    return cursor.fetchone()


def insertar_ticker(cursor, ticker_data):
    """Inserta un nuevo ticker en stage.cat_tickers"""
    try:
        cursor.execute(
            """
            INSERT INTO stage.cat_tickers 
            (emisora, serie, nombre, bolsa, mercado, isin, activo, fecha_carga)
            VALUES (?, ?, ?, ?, ?, ?, 1, GETDATE())
            """,
            (
                ticker_data['emisora'],
                ticker_data['serie'],
                ticker_data['nombre'],
                ticker_data['bolsa'],
                ticker_data['mercado'],
                ticker_data['isin']
            )
        )
        
        # Obtener el ID generado
        cursor.execute("SELECT @@IDENTITY")
        ticker_id = cursor.fetchone()[0]
        
        return ticker_id
        
    except Exception as e:
        print(f"❌ Error insertando ticker {ticker_data['emisora_serie']}: {str(e)}")
        raise


def main():
    print("=" * 80)
    print("VERIFICACIÓN Y CONFIGURACIÓN DE TICKERS")
    print(f"Ejecutado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    conn = conectar_bd()
    cursor = conn.cursor()
    
    resultados = []
    
    try:
        for ticker_data in TICKERS_A_VERIFICAR:
            emisora_serie = ticker_data['emisora_serie']
            emisora = ticker_data['emisora']
            serie = ticker_data['serie']
            
            print(f"\n📊 Verificando {emisora_serie}...")
            print("-" * 80)
            
            # Verificar si existe
            resultado = verificar_ticker(cursor, emisora, serie)
            
            if resultado:
                ticker_id, emisora_db, serie_db, nombre = resultado
                print(f"✅ Ya existe en la base de datos")
                print(f"   ticker_id: {ticker_id}")
                print(f"   Emisora: {emisora_db}, Serie: {serie_db}")
                print(f"   Nombre: {nombre}")
                resultados.append({
                    'ticker': emisora_serie,
                    'status': 'EXISTS',
                    'ticker_id': ticker_id
                })
            else:
                print(f"⚠️  No existe, insertando...")
                ticker_id = insertar_ticker(cursor, ticker_data)
                conn.commit()
                print(f"✅ Insertado exitosamente")
                print(f"   ticker_id: {ticker_id}")
                print(f"   Nombre: {ticker_data['nombre']}")
                resultados.append({
                    'ticker': emisora_serie,
                    'status': 'INSERTED',
                    'ticker_id': ticker_id
                })
        
        # Resumen
        print("\n" + "=" * 80)
        print("RESUMEN")
        print("=" * 80)
        
        for res in resultados:
            status_emoji = "✅" if res['status'] == 'EXISTS' else "🆕"
            status_text = "Ya existía" if res['status'] == 'EXISTS' else "Insertado"
            print(f"{status_emoji} {res['ticker']:<12} | ticker_id: {res['ticker_id']:<6} | {status_text}")
        
        print("\n✅ Todos los tickers están listos para usar en los ETL")
        print("=" * 80)
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)
    
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
