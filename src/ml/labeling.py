"""
Triple-Barrier Labeling + Sample Uniqueness Weights.

Metodología de López de Prado ("Advances in Financial Machine Learning", Cap. 3-4).

Idea central:
  En vez de etiquetar "¿subió en H días?" (label fijo en el tiempo),
  etiquetamos como realmente operamos:

    Desde el precio de entrada en t, se ponen 3 barreras:
      - Superior (target):  entry * (1 + mult_target * vol)   → label +1
      - Inferior (stop):    entry * (1 - mult_stop   * vol)   → label  0 (perdió)
      - Vertical (tiempo):  t + horizon días                  → label según signo

    La primera barrera tocada define el resultado.

Esto produce labels que coinciden con la estrategia real (stops ATR + targets),
en vez de un target arbitrario que ignora cómo cerramos posiciones.

Uso:
    from src.ml.labeling import triple_barrier_labels

    labels = triple_barrier_labels(
        close=raw["Close"], high=raw["High"], low=raw["Low"],
        vol=atr_pct_series, horizon=5,
        mult_target=1.5, mult_stop=1.5,
    )
    # labels["label"]:   1 = ganó (tocó target o cerró arriba)
    #                    0 = perdió (tocó stop o cerró abajo)
    # labels["touch"]:   "target" | "stop" | "time"
    # labels["ret"]:     retorno realizado del trade
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier_labels(
    close:       pd.Series,
    high:        pd.Series,
    low:         pd.Series,
    vol:         pd.Series,
    horizon:     int   = 5,
    mult_target: float = 1.5,
    mult_stop:   float = 1.5,
) -> pd.DataFrame:
    """
    Calcula labels triple-barrier para cada fecha de la serie.

    Args:
        close:       Serie de precios de cierre (índice temporal).
        high:        Serie de máximos diarios.
        low:         Serie de mínimos diarios.
        vol:         Volatilidad relativa por fila (ej. atr_pct = ATR/precio).
                     Define el ancho de las barreras.
        horizon:     Días hábiles hasta la barrera vertical.
        mult_target: Múltiplo de vol para la barrera superior (target).
        mult_stop:   Múltiplo de vol para la barrera inferior (stop).

    Returns:
        DataFrame alineado con `close` con columnas:
          - label  (int):   1 = trade ganador, 0 = perdedor
          - touch  (str):   "target" | "stop" | "time"
          - ret    (float): retorno realizado (%) del trade
          - bars   (int):   barras hasta el cierre del trade
    """
    n = len(close)
    idx = close.index

    c = close.values
    h = high.values
    l = low.values
    v = vol.values

    labels = np.full(n, np.nan)
    touches = np.empty(n, dtype=object)
    rets    = np.full(n, np.nan)
    bars    = np.full(n, np.nan)

    for i in range(n):
        if i + 1 >= n or np.isnan(v[i]) or v[i] <= 0:
            continue

        # Entrada = apertura del día siguiente (proxy: cierre actual)
        entry = c[i]
        up    = entry * (1 + mult_target * v[i])
        dn    = entry * (1 - mult_stop   * v[i])

        end = min(i + horizon, n - 1)

        touched = None
        exit_price = c[end]
        nbars = end - i

        # Recorrer la ventana buscando la primera barrera tocada
        for j in range(i + 1, end + 1):
            if h[j] >= up:
                touched, exit_price, nbars = "target", up, j - i
                break
            if l[j] <= dn:
                touched, exit_price, nbars = "stop", dn, j - i
                break

        if touched is None:
            # Barrera vertical: clasificar por signo del retorno
            touched = "time"
            exit_price = c[end]

        ret = (exit_price - entry) / entry * 100
        labels[i]  = 1 if ret > 0 else 0
        touches[i] = touched
        rets[i]    = ret
        bars[i]    = nbars

    return pd.DataFrame({
        "label": labels,
        "touch": touches,
        "ret":   rets,
        "bars":  bars,
    }, index=idx)


def sample_uniqueness_weights(
    bars: pd.Series,
    horizon: int = 5,
) -> pd.Series:
    """
    Pesos de unicidad (López de Prado, Cap. 4).

    Observaciones cuyos labels se solapan en el tiempo aportan información
    redundante. Este peso reduce la influencia de observaciones con mucho
    solapamiento, evitando que el modelo sobre-aprenda períodos densos.

    Aproximación práctica: el peso es inversamente proporcional a cuántas
    otras observaciones comparten el mismo período de holding.

    Args:
        bars:    Serie con el número de barras que duró cada trade.
        horizon: Horizonte máximo (para normalizar).

    Returns:
        Serie de pesos normalizados (media ≈ 1.0).
    """
    # Concurrencia: cuántos trades están "abiertos" en cada barra
    n = len(bars)
    concurrency = np.ones(n)
    b = bars.fillna(horizon).values.astype(int)

    counts = np.zeros(n + horizon + 1)
    for i in range(n):
        span = max(1, b[i])
        for j in range(i, min(i + span, n)):
            counts[j] += 1

    weights = np.ones(n)
    for i in range(n):
        span = max(1, b[i])
        # Peso = promedio de 1/concurrencia sobre el período de holding
        w = np.mean([1.0 / counts[j] for j in range(i, min(i + span, n)) if counts[j] > 0])
        weights[i] = w if w > 0 else 1.0

    s = pd.Series(weights, index=bars.index)
    # Normalizar para que la media sea 1
    return s / s.mean()


def barrier_stats(labels: pd.DataFrame) -> dict:
    """Resumen de la distribución de labels y barreras tocadas."""
    valid = labels.dropna(subset=["label"])
    if len(valid) == 0:
        return {}
    touch_dist = valid["touch"].value_counts(normalize=True).to_dict()
    return {
        "n":             len(valid),
        "win_rate":      round(valid["label"].mean(), 4),
        "avg_ret":       round(valid["ret"].mean(), 4),
        "avg_bars":      round(valid["bars"].mean(), 2),
        "pct_target":    round(touch_dist.get("target", 0), 4),
        "pct_stop":      round(touch_dist.get("stop", 0), 4),
        "pct_time":      round(touch_dist.get("time", 0), 4),
    }
