#!/usr/bin/env python3
"""
Test de carga histórica local (sin BD)
Verifica que Yahoo Finance tenga los datos de 1 año atrás
"""
import yfinance as yf
from datetime import datetime, timedelta

def test_historico_ticker(ticker_symbol, fecha_inicio, fecha_fin):
    """Prueba carga histórica de un ticker"""
    print(f"\n{'='*80}")
    print(f"📊 {ticker_symbol}")
    print(f"{'='*80}")
    
    try:
        # Descargar datos de Yahoo Finance
        stock = yf.Ticker(f"{ticker_symbol}.MX")
        hist = stock.history(start=fecha_inicio, end=fecha_fin)
        
        if hist.empty:
            print(f"❌ No se obtuvieron datos para {ticker_symbol}")
            return False
        
        # Estadísticas
        total_registros = len(hist)
        primera_fecha = hist.index[0].strftime('%Y-%m-%d')
        ultima_fecha = hist.index[-1].strftime('%Y-%m-%d')
        registros_con_volumen = (hist['Volume'] > 0).sum()
        registros_sin_volumen = (hist['Volume'] == 0).sum()
        
        print(f"\n✅ Datos obtenidos exitosamente:")
        print(f"   Total registros: {total_registros}")
        print(f"   Primera fecha: {primera_fecha}")
        print(f"   Última fecha: {ultima_fecha}")
        print(f"   Con volumen > 0: {registros_con_volumen}")
        print(f"   Con volumen = 0: {registros_sin_volumen}")
        
        # Mostrar primeros 5 registros
        print(f"\n📋 Primeros 5 registros:")
        print("-" * 80)
        print(f"{'Fecha':<12} | {'Open':>8} | {'High':>8} | {'Low':>8} | {'Close':>8} | {'Volume':>12}")
        print("-" * 80)
        for idx, row in hist.head(5).iterrows():
            fecha = idx.strftime('%Y-%m-%d')
            print(f"{fecha:<12} | ${row['Open']:>7.2f} | ${row['High']:>7.2f} | ${row['Low']:>7.2f} | ${row['Close']:>7.2f} | {row['Volume']:>12,.0f}")
        
        # Mostrar últimos 5 registros
        print(f"\n📋 Últimos 5 registros:")
        print("-" * 80)
        print(f"{'Fecha':<12} | {'Open':>8} | {'High':>8} | {'Low':>8} | {'Close':>8} | {'Volume':>12}")
        print("-" * 80)
        for idx, row in hist.tail(5).iterrows():
            fecha = idx.strftime('%Y-%m-%d')
            print(f"{fecha:<12} | ${row['Open']:>7.2f} | ${row['High']:>7.2f} | ${row['Low']:>7.2f} | ${row['Close']:>7.2f} | {row['Volume']:>12,.0f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("TEST DE CARGA HISTÓRICA - 1 AÑO")
    print(f"Ejecutado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Definir fechas (1 año: del 27 dic 2024 al 26 dic 2025)
    fecha_inicio = "2024-12-27"
    fecha_fin = "2025-12-27"  # Yahoo Finance usa end exclusive
    
    print(f"\n📅 Rango de fechas: {fecha_inicio} hasta {fecha_fin}")
    
    # Tickers a probar
    tickers = ["WALMEX*", "ALSEA*", "ALFAA"]
    
    resultados = {}
    for ticker in tickers:
        # Convertir ticker a formato Yahoo Finance
        ticker_yf = ticker.replace("*", "")
        resultados[ticker] = test_historico_ticker(ticker_yf, fecha_inicio, fecha_fin)
    
    # Resumen
    print(f"\n{'='*80}")
    print("RESUMEN")
    print(f"{'='*80}")
    for ticker, exito in resultados.items():
        status = "✅ EXITOSO" if exito else "❌ FALLIDO"
        print(f"{ticker}: {status}")
    
    print(f"\n{'='*80}")
    print("CONCLUSIÓN:")
    print("Si todos los tickers muestran ✅ EXITOSO, los datos están disponibles")
    print("y podemos proceder a cargarlos en la base de datos del servidor Windows")
    print(f"{'='*80}")
