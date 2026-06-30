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
    "id_vol_ratio",  # volumen intradía vs media móvil 20d (si hay volume)
    "id_gap",        # gap de apertura: 1er bar vs cierre previo (%)
]

INTRADAY_FEATURE_COLS: list[str] = list(INTRADAY_COLS)


def _day_features(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    prev_close: float | None = None,
    vol_avg_20d: float | None = None,
) -> dict | None:
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
    last_hr = (prices[-1] - prices[-k]) / (prices[-k] + 1e-9)
    first_hr = (prices[k - 1] - prices[0]) / (prices[0] + 1e-9)

    mid = n // 2
    am = (prices[mid] - prices[0]) / (prices[0] + 1e-9)
    pm = (prices[-1] - prices[mid]) / (prices[mid] + 1e-9)

    feats: dict[str, float] = {
        "id_ret": (cl - op) / (op + 1e-9) * 100,
        "id_range": rng * 100,
        "id_close_loc": (cl - lo) / (hi - lo + 1e-9),
        "id_rvol": rvol * 100,
        "id_last_hr": last_hr * 100,
        "id_first_hr": first_hr * 100,
        "id_up_frac": float((rets > 0).mean()),
        "id_pm_am": (pm - am) * 100,
        "id_vol_ratio": np.nan,
        "id_gap": np.nan,
    }

    if prev_close is not None and np.isfinite(prev_close) and prev_close > 0:
        feats["id_gap"] = (op - prev_close) / (prev_close + 1e-9) * 100

    if volumes is not None and vol_avg_20d is not None and vol_avg_20d > 0:
        day_vol = float(np.nansum(volumes))
        if np.isfinite(day_vol):
            feats["id_vol_ratio"] = day_vol / vol_avg_20d

    return feats


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

    has_volume = "volume" in df.columns and df["volume"].notna().any()

    recs: dict[pd.Timestamp, dict] = {}
    daily_vols: list[tuple[pd.Timestamp, float]] = []
    prev_close: float | None = None

    for date, grp in df.groupby("date", sort=True):
        prices = grp["price"].to_numpy(dtype=float)
        vols = grp["volume"].to_numpy(dtype=float) if has_volume else None
        day_vol = float(np.nansum(vols)) if vols is not None else np.nan
        if np.isfinite(day_vol):
            daily_vols.append((date, day_vol))

        vol_avg_20d: float | None = None
        if has_volume and daily_vols:
            recent = [v for _, v in daily_vols[-21:-1]]
            if recent:
                vol_avg_20d = float(np.mean(recent))

        feats = _day_features(
            prices,
            volumes=vols,
            prev_close=prev_close,
            vol_avg_20d=vol_avg_20d,
        )
        if feats is not None:
            recs[date] = feats
            prev_close = float(prices[-1])

    if not recs:
        return pd.DataFrame(columns=INTRADAY_COLS)
    out = pd.DataFrame(recs).T.sort_index()
    out.index = pd.to_datetime(out.index)
    return out[INTRADAY_COLS]


def compute_intraday_cs_medians(frames: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Mediana cross-seccional por columna intradía sobre un panel multi-ticker."""
    medians: dict[str, float] = {}
    for col in INTRADAY_COLS:
        parts = [
            frames[t][col]
            for t in frames
            if col in frames[t].columns
        ]
        if not parts:
            continue
        stacked = pd.concat(parts, ignore_index=True)
        medians[col] = float(stacked.median(skipna=True))
    return medians


def add_intraday_features(
    ticker_df: pd.DataFrame,
    ticker: str,
    cs_medians: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Añade features de microestructura intradía a un DataFrame diario por fecha.

    Imputación (post-merge):
      1. Forward-fill a lo largo del índice temporal (propaga la última señal
         intradía conocida hacia adelante).
      2. NaN restantes → mediana cross-seccional por columna cuando se pasa
         ``cs_medians`` (típico: mediana del panel multi-ticker en entrenamiento).
         Sin ``cs_medians``, los NaN iniciales (pre-nov-2024) permanecen NaN.

    Días sin intradía antes del histórico disponible quedan NaN hasta el ffill.
    """
    df = ticker_df.copy()
    df.index = pd.to_datetime(df.index)
    idf = compute_intraday_features(ticker)
    if idf.empty:
        for c in INTRADAY_COLS:
            df[c] = np.nan
    else:
        idf_aligned = idf.reindex(df.index.normalize())
        idf_aligned.index = df.index
        for c in INTRADAY_COLS:
            df[c] = idf_aligned[c]

    for c in INTRADAY_COLS:
        df[c] = df[c].ffill()
        if cs_medians and c in cs_medians and np.isfinite(cs_medians[c]):
            df[c] = df[c].fillna(cs_medians[c])

    return df
