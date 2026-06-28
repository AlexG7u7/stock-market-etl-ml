"""
Features de microestructura intradía — agregan barras 5m a señales DIARIAS.

A diferencia de los fundamentales (lentos, casi constantes por trimestre), la
microestructura intradía varía cada día y captura información ortogonal al
cierre diario: fuerza del cierre, volatilidad realizada, momentum de última
hora, drive de apertura. Estos patrones SÍ tienen poder predictivo de corto plazo.

Sin look-ahead: las features del día t usan solo barras del día t, que se conocen
al cierre de t — antes de la entrada (Open[t+1]) del modelo diario.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

INTRADAY_DIR = Path(__file__).parent.parent.parent / "data" / "intraday"

INTRADAY_COLS = [
    "id_ret",        # retorno open→close intradía
    "id_range",      # (high-low)/open  — rango relativo
    "id_close_loc",  # ubicación del cierre en el rango (0=mínimo, 1=máximo)
    "id_rvol",       # volatilidad realizada (std de retornos 5m)
    "id_last_hr",    # retorno de la última hora (momentum hacia el cierre)
    "id_first_hr",   # retorno de la primera hora (drive de apertura)
    "id_up_frac",    # fracción de barras alcistas
    "id_pm_am",      # retorno tarde menos retorno mañana
]


def _day_features(prices: np.ndarray) -> dict | None:
    """Microestructura de un día a partir del vector de precios 5m ordenado."""
    n = len(prices)
    if n < 6:
        return None
    op, cl = prices[0], prices[-1]
    hi, lo = prices.max(), prices.min()
    rng = (hi - lo) / (op + 1e-9)

    rets = np.diff(prices) / (prices[:-1] + 1e-9)
    rvol = float(np.std(rets)) if len(rets) > 1 else 0.0

    k = min(12, n // 3)  # ~última/primera hora (12 barras de 5m)
    last_hr  = (prices[-1] - prices[-k]) / (prices[-k] + 1e-9)
    first_hr = (prices[k - 1] - prices[0]) / (prices[0] + 1e-9)

    mid = n // 2
    am = (prices[mid] - prices[0])   / (prices[0] + 1e-9)
    pm = (prices[-1]  - prices[mid]) / (prices[mid] + 1e-9)

    return {
        "id_ret":       (cl - op) / (op + 1e-9) * 100,
        "id_range":     rng * 100,
        "id_close_loc": (cl - lo) / (hi - lo + 1e-9),
        "id_rvol":      rvol * 100,
        "id_last_hr":   last_hr * 100,
        "id_first_hr":  first_hr * 100,
        "id_up_frac":   float((rets > 0).mean()),
        "id_pm_am":     (pm - am) * 100,
    }


def compute_intraday_features(ticker: str) -> pd.DataFrame:
    """
    Carga las barras 5m de un ticker y agrega a features diarias.
    Devuelve DataFrame indexado por fecha (normalizada) con INTRADAY_COLS.
    DataFrame vacío si no hay datos.
    """
    path = INTRADAY_DIR / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=INTRADAY_COLS)

    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.normalize()
    df = df.sort_values("datetime")

    recs = {}
    for date, grp in df.groupby("date"):
        feats = _day_features(grp["price"].to_numpy(dtype=float))
        if feats is not None:
            recs[date] = feats

    if not recs:
        return pd.DataFrame(columns=INTRADAY_COLS)
    out = pd.DataFrame(recs).T.sort_index()
    out.index = pd.to_datetime(out.index)
    return out[INTRADAY_COLS]


def add_intraday_features(ticker_df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Añade features de microestructura intradía a un DataFrame diario por fecha.
    Días sin intradía (antes de nov-2024) quedan NaN.
    """
    df = ticker_df.copy()
    df.index = pd.to_datetime(df.index)
    idf = compute_intraday_features(ticker)
    if idf.empty:
        for c in INTRADAY_COLS:
            df[c] = np.nan
        return df
    # Alinear por fecha normalizada (las features de t describen el día t)
    idf_aligned = idf.reindex(df.index.normalize())
    idf_aligned.index = df.index
    for c in INTRADAY_COLS:
        df[c] = idf_aligned[c]
    return df
