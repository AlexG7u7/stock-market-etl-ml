"""
Probar request específico a Yahoo Finance para el 26 de diciembre 2025
"""
import yfinance as yf
from datetime import datetime, timedelta

ticker = "ALFAA.MX"

print("="*80)
print("TEST: Solicitar datos específicos del 26 de diciembre 2025")
print("="*80)

# Solicitar específicamente del 26 de diciembre
fecha_objetivo = "2025-12-26"

print(f"\n📊 Ticker: {ticker}")
print(f"📅 Fecha solicitada: {fecha_objetivo}")
print("-"*80)

try:
    stock = yf.Ticker(ticker)
    
    # Opción 1: Usar rango específico (26 al 27)
    print(f"\n1️⃣ Intentando con rango: 2025-12-26 a 2025-12-27")
    hist1 = stock.history(start="2025-12-26", end="2025-12-27")
    
    if not hist1.empty:
        print(f"   ✅ Devolvió {len(hist1)} registro(s)")
        for date, row in hist1.iterrows():
            fecha_str = date.strftime('%Y-%m-%d')
            print(f"   {fecha_str}: Close=${row['Close']:.2f}, Volume={int(row['Volume']):,}")
    else:
        print(f"   ❌ Sin datos")
    
    # Opción 2: Últimos 3 días
    print(f"\n2️⃣ Intentando últimos 3 días (period='3d')")
    hist2 = stock.history(period="3d")
    
    if not hist2.empty:
        print(f"   ✅ Devolvió {len(hist2)} registro(s)")
        for date, row in hist2.iterrows():
            fecha_str = date.strftime('%Y-%m-%d')
            print(f"   {fecha_str}: Close=${row['Close']:.2f}, Volume={int(row['Volume']):,}")
    else:
        print(f"   ❌ Sin datos")
    
    # Opción 3: Última semana completa
    print(f"\n3️⃣ Intentando última semana (2025-12-20 a 2025-12-27)")
    hist3 = stock.history(start="2025-12-20", end="2025-12-27")
    
    if not hist3.empty:
        print(f"   ✅ Devolvió {len(hist3)} registro(s)")
        for date, row in hist3.iterrows():
            fecha_str = date.strftime('%Y-%m-%d')
            volumen_str = f"{int(row['Volume']):,}" if row['Volume'] > 0 else "0 (SIN TRANSACCIONES)"
            print(f"   {fecha_str}: Close=${row['Close']:.2f}, Volume={volumen_str}")
    else:
        print(f"   ❌ Sin datos")
    
    # Análisis
    print("\n" + "="*80)
    print("📋 ANÁLISIS:")
    print("="*80)
    
    # Verificar si 26 dic está en alguna respuesta
    tiene_26_dic = False
    
    for hist in [hist1, hist2, hist3]:
        if not hist.empty:
            for date, row in hist.iterrows():
                if date.strftime('%Y-%m-%d') == fecha_objetivo:
                    tiene_26_dic = True
                    print(f"✅ Yahoo Finance SÍ tiene datos del {fecha_objetivo}")
                    print(f"   Close: ${row['Close']:.2f}")
                    print(f"   Volume: {int(row['Volume']):,}")
                    
                    if row['Volume'] == 0:
                        print(f"   ⚠️  PERO volumen = 0 (mercado cerrado, sin transacciones)")
                    break
        if tiene_26_dic:
            break
    
    if not tiene_26_dic:
        print(f"❌ Yahoo Finance NO tiene datos del {fecha_objetivo}")
        print(f"   Posibles razones:")
        print(f"   1. Día no bursátil (fin de semana o festivo)")
        print(f"   2. Datos aún no disponibles")
        print(f"   3. Yahoo Finance no publicó información para ese día")
        
        # Mostrar última fecha disponible
        if not hist3.empty:
            ultima_fecha = hist3.index[-1].strftime('%Y-%m-%d')
            print(f"\n   📅 Última fecha disponible: {ultima_fecha}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("CONCLUSIÓN:")
print("="*80)
print("""
Si Yahoo Finance devuelve datos con volumen=0, significa:
- La fecha existe en su sistema
- PERO no hubo sesión bursátil (mercado cerrado)
- El precio mostrado es el último conocido (carry-forward)

Si NO devuelve datos:
- La fecha no existe en su sistema
- Probablemente fin de semana o Yahoo aún no procesó esa fecha
""")
