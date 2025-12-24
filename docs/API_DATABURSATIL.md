# DataBursátil API Integration Guide

Guía de integración con la API de DataBursátil para datos de mercado bursátil mexicano.

---

## 📖 Documentación Oficial

**Base URL:** `https://api.databursatil.com`  
**Versión:** v2 (actual)  
**Documentación:** https://databursatil.com/docs.html  
**Status:** https://status.databursatil.com  
**Soporte:** hola@databursatil.com

---

## 🔐 Autenticación

### Obtener API Token

1. Registrarse en https://databursatil.com/signup
2. Ir a Dashboard → API Keys
3. Crear nuevo token con permisos: `read:historical`, `read:quotes`
4. Copiar token (solo se muestra una vez)

### Usar Token en Requests

```python
import requests

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

response = requests.get("https://api.databursatil.com/api/v1/tickers", headers=headers)
```

---

## 📡 Endpoints Principales

### 1. Históricos (OHLCV) - `/v2/historicos`

**Endpoint:** `GET /v2/historicos`

**Descripción:** Obtén precios históricos al cierre de la emisora y serie solicitada.

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `token` | string | ✅ | Token de autenticación (30 caracteres alfanuméricos) |
| `emisora_serie` | string | ✅ | Emisora con serie (ej: AMXL, WALMEX*, CEMEXCPO). Solo 1 por request. |
| `inicio` | date | ✅ | Fecha inicio (YYYY-MM-DD) |
| `final` | date | ✅ | Fecha fin (YYYY-MM-DD) |

**Ejemplo Request:**

```bash
curl "https://api.databursatil.com/v2/historicos?token=YOUR_TOKEN&emisora_serie=WALMEX*&inicio=2025-01-01&final=2025-12-24"
```

**Ejemplo Response:**

```json
{
  "2025-12-24": {
    "precio": 68.50,
    "importe": 1234567890
  },
  "2025-12-23": {
    "precio": 68.20,
    "importe": 987654321
  },
  "2025-12-20": {
    "precio": 67.85,
    "importe": 1100000000
  }
}
```

**Notas:**
- Solo devuelve precio de cierre e importe operado
- Para obtener OHLC completo, usar `/v2/intradia` con intervalo 1D
- Respuesta en formato `{fecha: {precio, importe}}`

---

### 2. Emisoras - `/v2/emisoras`

**Endpoint:** `GET /v2/emisoras`

**Descripción:** Información general de emisoras y sus series. Útil para seed de `silver.tickers`.

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `token` | string | ✅ | Token de autenticación |
| `letra` | string | ❌ | Filtrar por letra inicial o palabra completa |
| `mercado` | string | ❌ | "local" y/o "global" (separado por comas) |

**Ejemplo Request:**

```bash
curl "https://api.databursatil.com/v2/emisoras?token=YOUR_TOKEN&mercado=local"
```

**Ejemplo Response:**

```json
{
  "WALMEX": {
    "*": {
      "razon_social": "Walmart de México S.A.B. de C.V.",
      "isin": "MXP985471069",
      "bolsa": "BMV",
      "tipo_valor_descripcion": "Acciones",
      "tipo_valor_id": "1",
      "estatus": "Activa",
      "acciones_en_circulacion": 16450000000,
      "rango_historicos": "1995-01-02 a 2025-12-24",
      "rango_financieros": "1T_2010 a 3T_2025"
    }
  },
  "AMXL": {
    "": {
      "razon_social": "América Móvil S.A.B. de C.V.",
      "bolsa": "BMV",
      "sector": "Telecommunications"
    }
  }
}
```

---

### 3. Intradia (OHLC Completo) - `/v2/intradia`

**Endpoint:** `GET /v2/intradia`

**Descripción:** Historico de cotizaciones durante la jornada bursátil. **Usar esto para OHLC completo**.

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `token` | string | ✅ | Token de autenticación |
| `emisora_serie` | string | ✅ | Hasta 10 emisoras separadas por comas |
| `bolsa` | string | ✅ | "BMV" y/o "BIVA" (separadas por comas) |
| `intervalo` | string | ✅ | "1m", "5m", "1h", o "1d" |
| `inicio` | date | ✅ | Fecha inicio (YYYY-MM-DD) |
| `final` | date | ✅ | Fecha fin (YYYY-MM-DD) |

**Ejemplo para OHLC diario:**

```bash
curl "https://api.databursatil.com/v2/intradia?token=YOUR_TOKEN&emisora_serie=WALMEX*&bolsa=BMV&intervalo=1d&inicio=2025-12-01&final=2025-12-24"
```

**Nota:** Para obtener Open, High, Low, Close completo, usar intervalo "1d" con este endpoint.

---

### 4. Cotizaciones (Tiempo Real) - `/v2/cotizaciones`

**Endpoint:** `GET /v2/cotizaciones`

**Descripción:** Precios más recientes (intraday).

**Parámetros:**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `token` | string | ✅ | Token |
| `emisora_serie` | string | ✅ | Hasta 50 emisoras separadas por comas |
| `concepto` | string | ✅ | u,p,a,x,n,c,m,v,o,i (último, ppp, anterior, max, min, cambio%, cambio$, vol, ops, importe) |
| `bolsa` | string | ✅ | "BMV" y/o "BIVA" |

**Ejemplo:**

```bash
curl "https://api.databursatil.com/v2/cotizaciones?token=YOUR_TOKEN&emisora_serie=WALMEX*,AMXL&concepto=u,p,a,x,n,c,m,v,o,i&bolsa=BMV"
```

---

## ⚙️ Créditos y Rate Limits

DataBursátil usa un sistema de **créditos por KiB transferido**:

- **200,000 créditos mensuales** por usuario (plan gratuito)
- **1 crédito = 1 KiB** (1024 bytes) de datos transferidos
- Renovación: **1 de cada mes a las 00:01 CDT**

### Consultar Créditos Disponibles

```bash
curl "https://api.databursatil.com/v2/creditos?token=YOUR_TOKEN"
```

Response:
```json
{
  "disponibles": "195432"
}
```

### HTTP Headers

No hay headers especiales de rate limit. El sistema rechaza requests cuando créditos = 0.

**Error cuando créditos agotados:**
```json
{
  "error": "Créditos insuficientes"
}
```

---

## 🐍 Python Client Example

### Cliente para DataBursátil v2

```python
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class DataBursatilClient:
    """Cliente para API de DataBursátil v2."""
    
    def __init__(self, api_token: str):
        self.base_url = "https://api.databursatil.com/v2"
        self.token = api_token
    
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Realizar request con token."""
        params['token'] = self.token
        url = f"{self.base_url}/{endpoint}"
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def get_historicos(
        self, 
        emisora_serie: str, 
        inicio: str, 
        final: str
    ) -> Dict:
        """
        Obtener precios históricos al cierre.
        
        Args:
            emisora_serie: Emisora con serie (ej: "WALMEX*", "AMXL")
            inicio: Fecha inicio YYYY-MM-DD
            final: Fecha fin YYYY-MM-DD
            
        Returns:
            Dict con {fecha: {precio, importe}}
        """
        params = {
            "emisora_serie": emisora_serie,
            "inicio": inicio,
            "final": final
        }
        return self._make_request("historicos", params)
    
    def get_intradia_ohlc(
        self,
        emisora_serie: str,
        bolsa: str,
        inicio: str,
        final: str,
        intervalo: str = "1d"
    ) -> Dict:
        """
        Obtener OHLC completo usando endpoint intradia.
        
        Args:
            emisora_serie: Hasta 10 emisoras separadas por comas
            bolsa: "BMV" o "BIVA"
            inicio: Fecha inicio YYYY-MM-DD
            final: Fecha fin YYYY-MM-DD
            intervalo: "1m", "5m", "1h", "1d"
            
        Returns:
            Dict con cotizaciones
        """
        params = {
            "emisora_serie": emisora_serie,
            "bolsa": bolsa,
            "intervalo": intervalo,
            "inicio": inicio,
            "final": final
        }
        return self._make_request("intradia", params)
    
    def get_emisoras(
        self, 
        mercado: str = "local",
        letra: Optional[str] = None
    ) -> Dict:
        """
        Listar emisoras disponibles.
        
        Args:
            mercado: "local" y/o "global"
            letra: Filtrar por letra inicial
            
        Returns:
            Dict con información de emisoras
        """
        params = {"mercado": mercado}
        if letra:
            params["letra"] = letra
        return self._make_request("emisoras", params)
    
    def get_cotizaciones(
        self,
        emisora_serie: str,
        bolsa: str,
        concepto: str = "u,p,a,x,n,c,m,v,o,i"
    ) -> Dict:
        """
        Obtener cotizaciones en tiempo real.
        
        Args:
            emisora_serie: Hasta 50 emisoras separadas por comas
            bolsa: "BMV" y/o "BIVA"
            concepto: Conceptos separados por comas
            
        Returns:
            Dict con cotizaciones
        """
        params = {
            "emisora_serie": emisora_serie,
            "bolsa": bolsa,
            "concepto": concepto
        }
        return self._make_request("cotizaciones", params)
    
    def get_creditos(self) -> int:
        """Obtener créditos disponibles."""
        result = self._make_request("creditos", {})
        return int(result.get("disponibles", 0))


# ============================================
# Uso del cliente
# ============================================

# Inicializar
client = DataBursatilClient(api_token="YOUR_TOKEN_HERE")

# 1. Obtener históricos (solo precio de cierre)
historicos = client.get_historicos(
    emisora_serie="WALMEX*",
    inicio="2025-01-01",
    final="2025-12-24"
)
print(historicos)
# Output: {"2025-12-24": {"precio": 68.50, "importe": 123456}, ...}

# 2. Obtener OHLC completo con intradia
ohlc = client.get_intradia_ohlc(
    emisora_serie="WALMEX*",
    bolsa="BMV",
    inicio="2025-12-01",
    final="2025-12-24",
    intervalo="1d"  # Diario
)

# 3. Listar emisoras para seed de tickers
emisoras = client.get_emisoras(mercado="local")
for ticker, data in emisoras.items():
    for serie, info in data.items():
        print(f"{ticker}{serie}: {info.get('razon_social')}")

# 4. Cotizaciones en tiempo real
quote = client.get_cotizaciones(
    emisora_serie="WALMEX*,AMXL",
    bolsa="BMV",
    concepto="u,p,a,x,n,v"
)

# 5. Consultar créditos
creditos = client.get_creditos()
print(f"Créditos disponibles: {creditos}")
```

---

## 🔄 Manejo de Errores

### Códigos de Error Comunes

| Código | Significado | Acción |
|--------|-------------|--------|
| 401 | Unauthorized | Verificar token |
| 404 | Ticker not found | Verificar símbolo |
| 429 | Rate limit exceeded | Esperar retry_after segundos |
| 500 | Server error | Reintentar con backoff |

### Retry Logic

```python
import time
from requests.exceptions import HTTPError

def fetch_with_retry(client, ticker, max_retries=3):
    """Fetch con retry automático."""
    for attempt in range(max_retries):
        try:
            return client.get_historical(ticker, "2025-01-01", "2025-12-24")
        except HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                print(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
            elif e.response.status_code >= 500:
                wait_time = 2 ** attempt
                print(f"Server error. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
    
    raise Exception(f"Failed after {max_retries} retries")
```

---

## 📊 Tickers Principales BMV

### IPC (Índice de Precios y Cotizaciones)

| Ticker | Nombre | Sector |
|--------|--------|--------|
| AMXL | América Móvil | Telecommunications |
| WALMEX | Walmart de México | Retail |
| GFNORTEO | Grupo Financiero Banorte | Financial |
| CEMEXCPO | CEMEX | Materials |
| ALFAA | Alfa | Conglomerate |
| FEMSAUBD | FEMSA | Beverages |
| GMEXICOB | Grupo México | Mining |
| BIMBOA | Bimbo | Food |
| AC | Arca Continental | Beverages |
| ELEKTRA | Grupo Elektra | Retail |

---

## 🎯 Best Practices

1. **Caché de datos:** Almacenar respuestas exitosas para evitar llamadas redundantes
2. **Batch requests:** Agrupar múltiples tickers en lotes
3. **Incremental loads:** Solo fetch datos nuevos desde última carga
4. **Error logging:** Registrar todas las fallas de API
5. **Monitor rate limits:** Trackear uso de API

---

## 📞 Soporte

- **Email:** support@databursatil.com
- **Slack:** #databursatil-api
- **Status Page:** https://status.databursatil.com

---

## 📝 Changelog de la API

### v1.2 (2025-12-01)
- ✨ Agregado endpoint `/api/v1/dividends`
- 🐛 Fix en zona horaria para datos históricos
- ⚡ Mejora de performance en queries grandes

### v1.1 (2025-09-01)
- ✨ Soporte para mercado BIVA
- 📊 Nuevos sectores en metadata

### v1.0 (2025-06-01)
- 🎉 Lanzamiento inicial
