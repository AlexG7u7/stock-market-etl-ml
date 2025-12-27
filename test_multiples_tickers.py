"""
Probar WALMEX para comparar con ALFAA
"""
import yfinance as yf
from datetime import datetime

tickers = [
    ("ALFAA.MX", "ALFAA"),
    ("WALMEX.MX", "WALMEX*"),
    ("AMXL.MX", "AMXL"),
    ("ALSEA.MX", "ALSEA*")
]

print("="*80)
print("TEST: Comparar múltiples tickers del BMV")
print("Rango: 2025-12-20 a 2025-12-27 (semana navideña)")
print("="*80)

for ticker_yahoo, ticker_bmv in tickers:
    print(f"\n📊 {ticker_bmv} ({ticker_yahoo})")
    print("-" * 80)
    
    try:
        stock = yf.Ticker(ticker_yahoo)
        hist = stock.history(start="2025-12-20", end="2025-12-27")
        
        if not hist.empty:
            print(f"✅ {len(hist)} registros")
            print(f"\nFecha       | Close   | Volume        | Estado")
            print("-" * 60)
            
            sesiones_reales = 0
            for date, row in hist.iterrows():
                fecha_str = date.strftime('%Y-%m-%d')
                volumen = int(row['Volume'])
                
                if volumen > 0:
                    estado = "✅ CON TRANSACCIONES"
                    sesiones_reales += 1
                else:
                    estado = "⚠️  SIN VOLUMEN (carry-forward)"
                
                print(f"{fecha_str} | ${row['Close']:6.2f} | {volumen:13,} | {estado}")
            
            print(f"\n📈 Sesiones con transacciones: {sesiones_reales}/{len(hist)}")
            
            # Última sesión real
            sesiones_con_vol = hist[hist['Volume'] > 0]
            if not sesiones_con_vol.empty:
                ultima_real = sesiones_con_vol.index[-1].strftime('%Y-%m-%d')
                print(f"📅 Última sesión real: {ultima_real}")
            else:
                print(f"⚠️  Sin sesiones reales en este rango")
        else:
            print("❌ Sin datos")
            
    except Exception as e:
        print(f"❌ Error: {e}")

print("\n" + "="*80)
print("CONCLUSIÓN:")
print("="*80)
print("""
Si todos los tickers muestran volumen=0 en las mismas fechas:
✅ Confirma que la BMV estuvo cerrada (no es problema del ticker)

Si algunos tienen volumen > 0:
⚠️  Indica que hubo sesión pero ese ticker específico no operó
""")
