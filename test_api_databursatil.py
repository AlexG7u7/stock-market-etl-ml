"""
Script de prueba para verificar endpoints de DataBursátil
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('DATABURSATIL_API_TOKEN')
print(f"Token: {token[:10]}...")

# Probar diferentes endpoints
endpoints_to_test = [
    {
        "name": "Intradia",
        "url": f"https://api.databursatil.com/v2/intradia?token={token}&emisora_serie=ALFAA&concepto=u,p,a,x,n,c,m,v,o,i&bolsa=bmv"
    },
    {
        "name": "Cotizaciones",
        "url": f"https://api.databursatil.com/v2/cotizaciones?token={token}&emisora_serie=ALFAA&concepto=u,p,a,x,n,c,m,v,o,i&bolsa=bmv"
    },
    {
        "name": "Históricos últimos 2 días",
        "url": f"https://api.databursatil.com/v2/historicos?token={token}&emisora_serie=ALFAA&inicio=2024-12-20&final=2024-12-26"
    }
]

print("\n" + "="*80)
print("PROBANDO ENDPOINTS DE DATABURSÁTIL")
print("="*80)

for test in endpoints_to_test:
    print(f"\n🧪 Probando: {test['name']}")
    print(f"URL: {test['url'][:100]}...")
    
    try:
        response = requests.get(test['url'], timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Respuesta exitosa")
            print(f"Keys: {list(data.keys())[:5]}")
            print(f"Muestra: {str(data)[:200]}...")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Respuesta: {response.text[:300]}")
            
    except Exception as e:
        print(f"❌ Excepción: {e}")

print("\n" + "="*80)
