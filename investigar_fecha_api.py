"""
Investigar por qué la API devuelve fecha antigua
"""
import requests
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

token = os.getenv('DATABURSATIL_API_TOKEN')

print("="*80)
print(f"HOY ES: {datetime.now().strftime('%Y-%m-%d')}")
print("="*80)

# Probar cotizaciones
url = f"https://api.databursatil.com/v2/cotizaciones?token={token}&emisora_serie=ALFAA&concepto=u,p,a,x,n,c,m,v,o,i&bolsa=bmv"
print(f"\n🔍 URL: {url[:120]}...")

try:
    response = requests.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Respuesta completa:")
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # Analizar fecha
        if 'ALFAA' in data and 'bmv' in data['ALFAA']:
            fecha = data['ALFAA']['bmv'].get('f')
            print(f"\n📅 Fecha en respuesta: {fecha}")
            print(f"⚠️  Diferencia: La API devuelve datos del {fecha}, no de hoy ({datetime.now().strftime('%Y-%m-%d')})")
    else:
        print(f"❌ Error: {response.text}")
        
except Exception as e:
    print(f"❌ Excepción: {e}")

# Probar históricos para ver últimas fechas disponibles
print("\n" + "="*80)
print("Probando endpoint de históricos para ver últimas fechas...")
print("="*80)

url_hist = f"https://api.databursatil.com/v2/historicos?token={token}&emisora_serie=ALFAA&inicio=2024-12-01&final=2024-12-27"
try:
    response = requests.get(url_hist, timeout=10)
    if response.status_code == 200:
        data = response.json()
        fechas = sorted(data.keys(), reverse=True)
        print(f"\n📊 Últimas 10 fechas disponibles en históricos:")
        for fecha in fechas[:10]:
            precio = data[fecha][0] if isinstance(data[fecha], list) else data[fecha]
            print(f"  {fecha}: ${precio}")
    else:
        print(f"❌ Error: {response.text}")
except Exception as e:
    print(f"❌ Excepción: {e}")

print("\n" + "="*80)
