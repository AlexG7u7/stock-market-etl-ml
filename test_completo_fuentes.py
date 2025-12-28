"""
Test completo: Comparar Yahoo Finance vs DataBursátil
Fechas disponibles HOY (28 diciembre 2025)
"""
import yfinance as yf
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

print("="*80)
print(f"TEST COMPLETO - Ejecutado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

# Tickers a probar
tickers_test = [
    ("WALMEX.MX", "WALMEX*"),
    ("ALSEA.MX", "ALSEA*"),
    ("ALFAA.MX", "ALFAA")
]

# ============================================================================
# PARTE 1: YAHOO FINANCE - Última semana completa
# ============================================================================
print("\n" + "="*80)
print("PARTE 1: YAHOO FINANCE - Últimos 10 días")
print("="*80)

for ticker_yahoo, ticker_bmv in tickers_test:
    print(f"\n📊 {ticker_bmv} ({ticker_yahoo})")
    print("-" * 80)
    
    try:
        stock = yf.Ticker(ticker_yahoo)
        hist = stock.history(period="10d")
        
        if not hist.empty:
            print(f"Fecha       | Close   | Volume        | Estado")
            print("-" * 70)
            
            for date, row in hist.iterrows():
                fecha_str = date.strftime('%Y-%m-%d')
                volumen = int(row['Volume'])
                estado = "✅ CON VOL" if volumen > 0 else "⚠️  VOL=0"
                print(f"{fecha_str} | ${row['Close']:6.2f} | {volumen:13,} | {estado}")
            
            # Última fecha
            ultima_fecha = hist.index[-1].strftime('%Y-%m-%d')
            print(f"\n📅 Última fecha: {ultima_fecha}")
        else:
            print("❌ Sin datos")
    except Exception as e:
        print(f"❌ Error: {e}")

# ============================================================================
# PARTE 2: DATABURSÁTIL - Últimos días disponibles
# ============================================================================
print("\n\n" + "="*80)
print("PARTE 2: DATABURSÁTIL API - Últimos 10 días")
print("="*80)

token = os.getenv('DATABURSATIL_API_TOKEN')

if token:
    # Probar con diferentes tickers
    for ticker_yahoo, ticker_bmv in tickers_test:
        print(f"\n📊 {ticker_bmv}")
        print("-" * 80)
        
        # Calcular rango de fechas (últimos 10 días)
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
        fecha_inicio = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        
        url = f"https://api.databursatil.com/v2/historicos?token={token}&emisora_serie={ticker_bmv}&inicio={fecha_inicio}&final={fecha_fin}"
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'Error' in data:
                    print(f"⚠️  Error API: {data.get('Error')}")
                else:
                    fechas = sorted(data.keys(), reverse=True)
                    
                    if fechas:
                        print(f"Fecha       | Precio  | Importe")
                        print("-" * 50)
                        
                        for fecha in fechas[:10]:  # Últimas 10
                            precio_data = data[fecha]
                            if isinstance(precio_data, list):
                                precio = precio_data[0]
                                importe = precio_data[1] if len(precio_data) > 1 else 0
                            else:
                                precio = precio_data
                                importe = 0
                            
                            print(f"{fecha} | ${precio:6.2f} | ${importe:,.0f}")
                        
                        print(f"\n📅 Última fecha: {fechas[0]}")
                    else:
                        print("⚠️  Sin datos en el rango")
            else:
                print(f"❌ Error HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
else:
    print("⚠️  Token de DataBursátil no encontrado en .env")

# ============================================================================
# RESUMEN COMPARATIVO
# ============================================================================
print("\n\n" + "="*80)
print("RESUMEN COMPARATIVO")
print("="*80)

print("""
📊 Análisis:
-----------
1. Revisa las últimas fechas disponibles en cada fuente
2. Compara Yahoo Finance vs DataBursátil
3. Verifica cuál tiene datos más recientes

Preguntas clave:
- ¿Tienen ambas fuentes datos del 27 dic 2025?
- ¿Cuál está más actualizada?
- ¿Hay diferencias significativas en los datos?
""")
