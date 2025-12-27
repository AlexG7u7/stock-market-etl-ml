"""
Comparar Yahoo Finance vs DataBursátil para datos de hoy
"""
import yfinance as yf
from datetime import datetime, timedelta

ticker_yahoo = "ALFAA.MX"  # Formato Yahoo Finance para BMV

print("="*80)
print(f"HOY ES: {datetime.now().strftime('%Y-%m-%d')}")
print("="*80)

# Obtener últimos 10 días de Yahoo Finance
print(f"\n📊 YAHOO FINANCE - {ticker_yahoo}")
print("-"*80)

try:
    stock = yf.Ticker(ticker_yahoo)
    
    # Obtener históricos de últimos 10 días
    hist = stock.history(period="10d")
    
    if not hist.empty:
        print(f"\n✅ Últimas {len(hist)} sesiones disponibles:\n")
        for date, row in hist.iterrows():
            fecha_str = date.strftime('%Y-%m-%d')
            print(f"  {fecha_str}: Open=${row['Open']:.2f}, Close=${row['Close']:.2f}, Volume={int(row['Volume']):,}")
        
        # Verificar si tiene datos de hoy
        ultima_fecha = hist.index[-1].strftime('%Y-%m-%d')
        hoy = datetime.now().strftime('%Y-%m-%d')
        
        print(f"\n📅 Última fecha disponible: {ultima_fecha}")
        
        if ultima_fecha == hoy:
            print(f"✅ Yahoo Finance TIENE datos de hoy ({hoy})")
        else:
            dias_diferencia = (datetime.now() - hist.index[-1]).days
            print(f"⚠️  Yahoo Finance NO tiene datos de hoy")
            print(f"   Última fecha: {ultima_fecha} ({dias_diferencia} días atrás)")
    else:
        print("❌ No hay datos disponibles")
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*80)
print("CONCLUSIÓN:")
print("="*80)
print("""
Si Yahoo Finance tiene datos más recientes que DataBursátil,
podemos:

1. Usar Yahoo Finance para el incremental diario (más actualizado)
2. Usar DataBursátil solo para validación o datos históricos

O bien:

3. Usar /v2/historicos de DataBursátil en lugar de /v2/cotizaciones
   (parece tener datos más actuales según el test anterior)
""")
