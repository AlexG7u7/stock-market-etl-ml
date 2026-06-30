"""
Universos de instrumentos disponibles en GBM — por clase de activo.

Cada universo define:
  - tickers: dict nombre_corto → símbolo yfinance
  - descripcion: qué es
  - moneda: MXN o USD
  - horizonte recomendado (días hábiles)
"""
from __future__ import annotations

from src.data.bmv_catalog import BMV_YFINANCE as BMV_ACCIONES

# ─── 2. Acciones USA (SIC / Trading USA) ──────────────────────────────────────
# Las más populares en GBM. Cotizan en MXN via SIC o en USD via Trading USA.
SIC_USA_ACCIONES = {
    # Tecnología
    "AAPL":   "AAPL",    "MSFT":   "MSFT",    "NVDA":   "NVDA",
    "GOOGL":  "GOOGL",   "META":   "META",    "AMZN":   "AMZN",
    "TSLA":   "TSLA",    "AMD":    "AMD",     "INTC":   "INTC",
    # Finanzas
    "JPM":    "JPM",     "BAC":    "BAC",     "GS":     "GS",
    "V":      "V",       "MA":     "MA",
    # Consumo / salud
    "KO":     "KO",      "PEP":    "PEP",     "MCD":    "MCD",
    "JNJ":    "JNJ",     "PFE":    "PFE",
    # Energía
    "XOM":    "XOM",     "CVX":    "CVX",
    # Latam / México en NYSE
    "AMX":    "AMX",     "FMX":    "FMX",     "BSMX":   "BSMX",
}

# ─── 3. ETFs (México + USA, disponibles en GBM) ───────────────────────────────
ETFS = {
    # México
    "NAFTRAC":  "NAFTRAC.MX",  # IPC ETF — benchmark MX
    "FIBRAPL":  "FIBRAPL14.MX",# FIBRA Prologis — logística
    # USA amplio mercado
    "SPY":      "SPY",         # S&P 500
    "QQQ":      "QQQ",         # Nasdaq 100
    "IWM":      "IWM",         # Russell 2000 (small caps)
    "VTI":      "VTI",         # Total US market
    "VOO":      "VOO",         # Vanguard S&P 500
    # Sectoriales USA
    "XLK":      "XLK",         # Tecnología
    "XLF":      "XLF",         # Finanzas
    "XLE":      "XLE",         # Energía
    "XLV":      "XLV",         # Salud
    "XLI":      "XLI",         # Industriales
    "XLY":      "XLY",         # Consumo discrecional
    "XLP":      "XLP",         # Consumo básico
    # Internacionales
    "EEM":      "EEM",         # Emergentes
    "EWZ":      "EWZ",         # Brasil
    "FXI":      "FXI",         # China
    # Commodities / cobertura
    "GLD":      "GLD",         # Oro
    "SLV":      "SLV",         # Plata
    "USO":      "USO",         # Petróleo WTI
    "TLT":      "TLT",         # Bonos USA largo plazo
    "HYG":      "HYG",         # High yield bonds
}

# ─── 4. Exposición cripto (ETFs y proxies en GBM) ─────────────────────────────
CRIPTO_PROXY = {
    # ETFs de Bitcoin/Ethereum (disponibles en GBM Trading USA)
    "IBIT":   "IBIT",    # BlackRock Bitcoin ETF (spot)
    "FBTC":   "FBTC",    # Fidelity Bitcoin ETF (spot)
    "ETHA":   "ETHA",    # BlackRock Ethereum ETF
    "GBTC":   "GBTC",    # Grayscale Bitcoin Trust
    # Acciones proxy de cripto
    "MSTR":   "MSTR",    # MicroStrategy — mayor holder de BTC corporativo
    "COIN":   "COIN",    # Coinbase — exchange
    "MARA":   "MARA",    # Marathon Digital — minería BTC
    "RIOT":   "RIOT",    # Riot Platforms — minería BTC
    "CLSK":   "CLSK",    # CleanSpark — minería
}

# ─── 5. FIBRAs (bienes raíces México) ─────────────────────────────────────────
FIBRAS = {
    "FUNO11":   "FUNO11.MX",    # FUNO — retail/oficinas
    "FIBRAPL":  "FIBRAPL14.MX", # Prologis — logística/industrial
    "TERRA13":  "TERRA13.MX",   # Terra — industrial/logística
    "FINN13":   "FINN13.MX",    # Finn — hotelería
    "MXOT":     "MXOT.MX",      # Macquarie — infraestructura
}

# ─── Metadatos de cada universo ───────────────────────────────────────────────
UNIVERSES = {
    "🇲🇽 Acciones BMV": {
        "slug": "bmv",
        "tickers": BMV_ACCIONES,
        "descripcion": "36 acciones líquidas BMV (IPC + extensión)",
        "moneda": "MXN",
        "horizonte": 20,
        "macro_benchmark": "NAFTRAC.MX",
        "min_tickers": 10,
    },
    "🇺🇸 Acciones USA (SIC)": {
        "slug": "usa",
        "tickers": SIC_USA_ACCIONES,
        "descripcion": "Acciones del NYSE y Nasdaq disponibles en GBM vía SIC o Trading USA",
        "moneda": "USD",
        "horizonte": 20,
        "macro_benchmark": "SPY",
        "min_tickers": 10,
    },
    "📦 ETFs": {
        "slug": "etfs",
        "tickers": ETFS,
        "descripcion": "ETFs de México y USA — rotación de sectores y clases de activo",
        "moneda": "USD/MXN",
        "horizonte": 20,
        "macro_benchmark": "SPY",
        "min_tickers": 8,
    },
    "₿ Cripto (proxies GBM)": {
        "slug": "cripto",
        "tickers": CRIPTO_PROXY,
        "descripcion": "ETFs de BTC/ETH y acciones del ecosistema cripto disponibles en GBM",
        "moneda": "USD",
        "horizonte": 10,   # más volátil → horizonte más corto
        "macro_benchmark": "IBIT",
        "min_tickers": 4,
    },
    "🏢 FIBRAs (bienes raíces MX)": {
        "slug": "fibras",
        "tickers": FIBRAS,
        "descripcion": "Fideicomisos de Infraestructura y Bienes Raíces en México",
        "moneda": "MXN",
        "horizonte": 20,
        "macro_benchmark": "FUNO11.MX",
        "min_tickers": 3,
    },
}

# Orden para el display en tabs
UNIVERSE_ORDER = list(UNIVERSES.keys())
