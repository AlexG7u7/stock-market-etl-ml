"""
Data store local — caché de datos OHLCV en Parquet.

Estructura:
  data/market/
    ALSEA.MX.parquet      — tickers BMV
    AAPL.parquet          — tickers USA (SIC)
    SPY.parquet           — ETFs
    IBIT.parquet          — Cripto (proxies)
    FUNO11.MX.parquet     — FIBRAs
    MXN=X.parquet         — macro: USD/MXN
    NAFTRAC.MX.parquet    — macro: IPC ETF
    CL=F.parquet          — macro: WTI
    ^GSPC.parquet         — macro: S&P 500

Cada parquet: Date (index), Open, High, Low, Close, Volume

Grupos:
    BMV_TICKERS     — acciones mexicanas (IPC + extensión)
    USA_TICKERS     — acciones USA disponibles en GBM SIC
    ETF_TICKERS     — ETFs listados en BMV / NYSE
    CRYPTO_TICKERS  — proxies de criptomonedas (ETFs/mineras)
    FIBRA_TICKERS   — FIBRAs mexicanas (REITs)
    MACRO_TICKERS   — USD/MXN, NAFTRAC, WTI, SP500
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

MARKET_DIR = Path(__file__).parent.parent.parent / "data" / "market"

BMV_TICKERS: dict[str, str] = {
    # ── IPC Core (originales, alta liquidez) ──────────────────────────────────
    "WALMEX":   "WALMEX.MX",   "FEMSAUBD": "FEMSAUBD.MX",
    "GMEXICOB": "GMEXICOB.MX", "CEMEXCPO": "CEMEXCPO.MX",
    "GFNORTEO": "GFNORTEO.MX", "BIMBOA":   "BIMBOA.MX",
    "ALSEA":    "ALSEA.MX",    "KIMBERA":  "KIMBERA.MX",
    "PINFRA":   "PINFRA.MX",   "ORBIA":    "ORBIA.MX",
    "GRUMAB":   "GRUMAB.MX",   "ASURB":    "ASURB.MX",
    "OMAB":     "OMAB.MX",     "GAPB":     "GAPB.MX",
    "GCARSOA1": "GCARSOA1.MX", "MEGACPO":  "MEGACPO.MX",
    "LABB":     "LABB.MX",     "Q":        "Q.MX",
    "VOLARA":   "VOLARA.MX",
    # ── Expansión (verificados en yfinance) ───────────────────────────────────
    "CUERVO":      "CUERVO.MX",     # José Cuervo — bebidas / tequila
    "AC":          "AC.MX",         # Arca Continental — Coca-Cola México
    "VESTA":       "VESTA.MX",      # Vesta — REIT industrial (parques logísticos)
    "VISTA":       "VISTAA.MX",     # Vista Energy — petróleo E&P
    "BOLSAA":      "BOLSAA.MX",     # Bolsa Mexicana — financiero
    "GCC":         "GCC.MX",        # GCC — cemento norte / EUA
    "HOTEL":       "HOTEL.MX",      # Hoteles City — turismo / hotelería
    "POSADAS":     "POSADASA.MX",   # Posadas — hotelería nacional
    "TLEVISA":     "TLEVISACPO.MX", # Televisa — media / telecomunicaciones
    "HERDEZ":      "HERDEZ.MX",     # Herdez — alimentos procesados
    "GENTERA":     "GENTERA.MX",    # Gentera — microfinanzas / bancarización
    "FUNO11":      "FUNO11.MX",     # FUNO — FIBRA retail (REIT)
}

USA_TICKERS: dict[str, str] = {
    # ── Tecnología ────────────────────────────────────────────────────────────
    "AAPL":  "AAPL",   # Apple
    "MSFT":  "MSFT",   # Microsoft
    "NVDA":  "NVDA",   # NVIDIA
    "GOOGL": "GOOGL",  # Alphabet
    "META":  "META",   # Meta Platforms
    "AMZN":  "AMZN",   # Amazon
    "TSLA":  "TSLA",   # Tesla
    "AMD":   "AMD",    # AMD
    "INTC":  "INTC",   # Intel
    # ── Financiero ───────────────────────────────────────────────────────────
    "JPM":   "JPM",    # JP Morgan
    "BAC":   "BAC",    # Bank of America
    "GS":    "GS",     # Goldman Sachs
    "V":     "V",      # Visa
    "MA":    "MA",     # Mastercard
    # ── Consumo / Salud ───────────────────────────────────────────────────────
    "KO":    "KO",     # Coca-Cola
    "PEP":   "PEP",    # PepsiCo
    "MCD":   "MCD",    # McDonald's
    "JNJ":   "JNJ",    # Johnson & Johnson
    "PFE":   "PFE",    # Pfizer
    # ── Energía ──────────────────────────────────────────────────────────────
    "XOM":   "XOM",    # ExxonMobil
    "CVX":   "CVX",    # Chevron
    # ── Latam/México en NYSE ──────────────────────────────────────────────────
    "AMX":   "AMX",    # América Móvil (ADR)
    "FMX":   "FMX",    # FEMSA (ADR)
    # BSMX excluido — delisted en Yahoo Finance
}

ETF_TICKERS: dict[str, str] = {
    # ── México ────────────────────────────────────────────────────────────────
    "NAFTRAC_ETF": "NAFTRACISHRS.MX",  # IPC (benchmark)
    "FIBRAPL_ETF": "FIBRAPL14.MX",     # FIBRA Prologis
    # ── USA broad market ──────────────────────────────────────────────────────
    "SPY":   "SPY",    # S&P 500
    "QQQ":   "QQQ",    # NASDAQ-100
    "IWM":   "IWM",    # Russell 2000 (small cap)
    "VTI":   "VTI",    # Total Stock Market
    "VOO":   "VOO",    # S&P 500 (Vanguard)
    # ── Sectores USA ─────────────────────────────────────────────────────────
    "XLK":   "XLK",    # Tecnología
    "XLF":   "XLF",    # Financiero
    "XLE":   "XLE",    # Energía
    "XLV":   "XLV",    # Salud
    "XLI":   "XLI",    # Industrial
    "XLY":   "XLY",    # Consumo discrecional
    "XLP":   "XLP",    # Consumo básico
    # ── Internacional ────────────────────────────────────────────────────────
    "EEM":   "EEM",    # Emergentes
    "EWZ":   "EWZ",    # Brasil
    "FXI":   "FXI",    # China
    # ── Commodities ──────────────────────────────────────────────────────────
    "GLD":   "GLD",    # Oro
    "SLV":   "SLV",    # Plata
    "USO":   "USO",    # Petróleo (WTI)
    # ── Renta fija ───────────────────────────────────────────────────────────
    "TLT":   "TLT",    # Bonos USA 20y+
    "HYG":   "HYG",    # High Yield
}

CRYPTO_TICKERS: dict[str, str] = {
    # ── ETFs de Bitcoin / Ethereum ────────────────────────────────────────────
    "IBIT":  "IBIT",   # iShares Bitcoin ETF (BlackRock)
    "FBTC":  "FBTC",   # Fidelity Bitcoin ETF
    "ETHA":  "ETHA",   # iShares Ethereum ETF
    "GBTC":  "GBTC",   # Grayscale Bitcoin Trust
    # ── Mineras y proxies ────────────────────────────────────────────────────
    "MSTR":  "MSTR",   # MicroStrategy (proxy BTC)
    "COIN":  "COIN",   # Coinbase
    "MARA":  "MARA",   # Marathon Digital (minera BTC)
    "RIOT":  "RIOT",   # Riot Platforms (minera BTC)
    "CLSK":  "CLSK",   # CleanSpark (minera BTC)
}

FIBRA_TICKERS: dict[str, str] = {
    "FUNO11":  "FUNO11.MX",   # FUNO — retail/oficinas (ya en BMV)
    "FIBRAPL": "FIBRAPL14.MX", # Fibra Prologis — industrial/logística
    "FINN13":  "FINN13.MX",   # Fibra Inn — hotelero
    # TERRA13.MX y MXOT.MX excluidos — delisted en Yahoo Finance
}

MACRO_TICKERS: dict[str, str] = {
    "USDMXN":   "MXN=X",
    "NAFTRAC":  "NAFTRAC.MX",
    "WTI":      "CL=F",
    "SP500":    "^GSPC",
}

# Índice completo de todos los símbolos del store
ALL_SYMBOLS = {
    **BMV_TICKERS,
    **USA_TICKERS,
    **ETF_TICKERS,
    **CRYPTO_TICKERS,
    **FIBRA_TICKERS,
    **MACRO_TICKERS,
}

# Grupos para ETL selectivo
UNIVERSE_GROUPS: dict[str, dict[str, str]] = {
    "bmv":    BMV_TICKERS,
    "usa":    USA_TICKERS,
    "etf":    ETF_TICKERS,
    "crypto": CRYPTO_TICKERS,
    "fibra":  FIBRA_TICKERS,
    "macro":  MACRO_TICKERS,
}


def _parquet_path(symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("^", "")
    return MARKET_DIR / f"{safe}.parquet"


def _download(symbol: str, start: str = "2000-01-01") -> pd.DataFrame:
    raw = yf.download(
        symbol, start=start, end=datetime.today().strftime("%Y-%m-%d"),
        auto_adjust=False, progress=False, actions=False,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = pd.to_datetime(raw.index)
    raw.index.name = "Date"
    cols = [c for c in ["Open","High","Low","Close","Volume"] if c in raw.columns]
    return raw[cols].dropna(how="all")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas con Close=0 o NaN en Close."""
    df = df[df["Close"].notna() & (df["Close"] > 0)].copy()
    # Forward-fill Volume vacío (algunos instrumentos macro no tienen volumen)
    if "Volume" in df.columns:
        df["Volume"] = df["Volume"].fillna(0)
    return df


# ─── Guardar / Cargar ─────────────────────────────────────────────────────────

def save(symbol: str, df: pd.DataFrame) -> None:
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    path = _parquet_path(symbol)
    df = _clean(df)
    df.to_parquet(path, compression="snappy")


def load(symbol: str) -> Optional[pd.DataFrame]:
    path = _parquet_path(symbol)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df


def needs_update(symbol: str, max_stale_days: int = 1) -> bool:
    path = _parquet_path(symbol)
    if not path.exists():
        return True
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).days >= max_stale_days


# ─── Update incremental ───────────────────────────────────────────────────────

def update(symbol: str, verbose: bool = True) -> pd.DataFrame:
    """
    Descarga historial completo si no existe, o solo los días nuevos si ya existe.
    Devuelve el DataFrame completo actualizado.
    """
    existing = load(symbol)

    if existing is None or len(existing) == 0:
        if verbose:
            print(f"  {symbol:<14} descargando historial completo...", end=" ")
        df = _download(symbol, start="2000-01-01")
    else:
        last_date = existing.index[-1]
        start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        new = _download(symbol, start=start)

        if len(new) == 0:
            if verbose:
                print(f"  {symbol:<14} ya actualizado ({len(existing):,} días)")
            return existing

        df = pd.concat([existing, new]).drop_duplicates()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if verbose:
            print(f"  {symbol:<14} +{len(new)} días nuevos  →  total {len(df):,}", end=" ")

    save(symbol, df)
    if verbose:
        print(f"  [{df.index[0].date()} → {df.index[-1].date()}]")
    return df


def update_all(verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Actualiza todos los símbolos de todos los universos."""
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for name, symbol in ALL_SYMBOLS.items():
        try:
            result[name] = update(symbol, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"  {symbol:<14} ERROR: {e}")
    return result


def update_group(group: str, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """
    Actualiza solo un grupo de símbolos.

    Parameters
    ----------
    group : "bmv" | "usa" | "etf" | "crypto" | "fibra" | "macro"
    """
    from src.data.store import UNIVERSE_GROUPS
    tickers = UNIVERSE_GROUPS.get(group, {})
    if not tickers:
        raise ValueError(f"Grupo desconocido: {group!r}. Opciones: {list(UNIVERSE_GROUPS)}")
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for name, symbol in tickers.items():
        try:
            result[name] = update(symbol, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"  {symbol:<14} ERROR: {e}")
    return result


# ─── Acceso conveniente ────────────────────────────────────────────────────────

def get(name: str) -> Optional[pd.DataFrame]:
    """Carga un símbolo por nombre (e.g. 'ALSEA', 'USDMXN', 'SP500')."""
    symbol = ALL_SYMBOLS.get(name, name)
    return load(symbol)


def get_close_matrix(names: list[str] | None = None) -> pd.DataFrame:
    """
    Devuelve una matriz de precios de cierre (Date × ticker).
    Útil para calcular correlaciones y retornos relativos.
    """
    if names is None:
        names = list(ALL_SYMBOLS.keys())
    closes = {}
    for name in names:
        df = get(name)
        if df is not None and "Close" in df.columns:
            closes[name] = df["Close"]
    return pd.DataFrame(closes).sort_index()


def info() -> None:
    """Imprime un resumen del estado del store."""
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    files = list(MARKET_DIR.glob("*.parquet"))
    total_size = sum(f.stat().st_size for f in files) / 1024 / 1024
    print(f"\n  Store: {MARKET_DIR}")
    print(f"  Archivos: {len(files)}  |  Tamaño total: {total_size:.1f} MB\n")
    for name, symbol in ALL_SYMBOLS.items():
        df = load(symbol)
        if df is not None:
            size_kb = _parquet_path(symbol).stat().st_size / 1024
            print(f"  {name:<12} {symbol:<16} {len(df):>6,} días  "
                  f"{df.index[0].date()} → {df.index[-1].date()}  "
                  f"({size_kb:.0f} KB)")
        else:
            print(f"  {name:<12} {symbol:<16} — no descargado")
    print()
