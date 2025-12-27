"""
Investigar fechas específicas 24-27 diciembre 2025
"""
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

ticker = "ALFAA.MX"

print("="*80)
print("INVESTIGACIÓN: ¿Por qué no hay datos del 26 de diciembre 2025?")
print("="*80)

# Obtener datos de diciembre 2025
print(f"\n📊 Consultando Yahoo Finance para {ticker}")
print(f"   Rango: 2025-12-20 a 2025-12-27")
print("-"*80)

try:
    stock = yf.Ticker(ticker)
    
    # Obtener históricos de diciembre
    hist = stock.history(start="2025-12-20", end="2025-12-28")  # end es exclusivo
    
    if not hist.empty:
        print(f"\n✅ Datos obtenidos: {len(hist)} registros\n")
        
        print("Fecha       | Día Semana | Open    | Close   | Volume      | Observación")
        print("-" * 90)
        
        for date, row in hist.iterrows():
            fecha_str = date.strftime('%Y-%m-%d')
            dia_semana = date.strftime('%A')  # Lunes, Martes, etc.
            volumen = int(row['Volume'])
            
            observacion = ""
            if volumen == 0:
                observacion = "⚠️ SIN VOLUMEN (mercado cerrado o sin transacciones)"
            elif volumen < 1000:
                observacion = "⚠️ Volumen muy bajo"
            elif fecha_str == "2025-12-24":
                observacion = "🎄 Nochebuena"
            elif fecha_str == "2025-12-25":
                observacion = "🎄 Navidad"
            elif fecha_str == "2025-12-26":
                observacion = "❓ Día después de Navidad"
            
            print(f"{fecha_str} | {dia_semana:10} | ${row['Open']:6.2f} | ${row['Close']:6.2f} | {volumen:11,} | {observacion}")
        
        # Verificar última fecha con volumen real
        fechas_con_volumen = hist[hist['Volume'] > 0]
        if not fechas_con_volumen.empty:
            ultima_real = fechas_con_volumen.index[-1].strftime('%Y-%m-%d')
            print(f"\n📅 Última sesión CON VOLUMEN: {ultima_real}")
        else:
            print(f"\n⚠️  No hay sesiones con volumen en este rango")
            
    else:
        print("❌ No hay datos disponibles")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Verificar si hoy es día hábil
print("\n" + "="*80)
print("CALENDARIO BMV - Días festivos diciembre 2025:")
print("="*80)
print("""
Días festivos oficiales en México (diciembre 2025):
- 25 diciembre: Navidad (jueves) - MERCADO CERRADO
- 1 enero: Año Nuevo (miércoles) - MERCADO CERRADO

Días laborables:
- 24 diciembre (miércoles): Usualmente MEDIO DÍA o cierre temprano
- 26 diciembre (jueves): Día normal (NO es festivo en México)
- 27 diciembre (viernes): Día normal

Si no hay datos del 26, puede ser porque:
1. Yahoo Finance aún no actualizó (puede tardar hasta el día siguiente)
2. La BMV tuvo sesión reducida o cerró temprano
3. Bajas transacciones en temporada navideña
""")

print("\n" + "="*80)
print("RECOMENDACIÓN:")
print("="*80)
print("""
Para ETL incremental en temporada navideña:
1. Ejecutar a las 6:00 PM en lugar de 4:00 PM (más margen)
2. El script con lookback_days=1 es correcto
3. Si no hay datos de HOY, insertará los últimos disponibles
4. No habrá duplicados gracias al UNIQUE constraint
""")
