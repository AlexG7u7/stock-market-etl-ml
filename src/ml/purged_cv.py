"""
Purged Walk-Forward Cross-Validation con Embargo.

Implementación propia de la metodología de López de Prado
("Advances in Financial Machine Learning", Cap. 7).

Conceptos clave:
  - Purging:   se eliminan del train las observaciones cuyo LABEL
               se solapa temporalmente con el test set.
               Para horizonte H=5 días, las últimas H filas de train
               se eliminan por cada fold.
  - Embargo:   se añade un buffer adicional entre train y test
               para evitar contaminación por autocorrelación.
               Típico: embargo = 0.01 × tamaño del dataset.

Uso:
    from src.ml.purged_cv import purged_walk_forward_splits

    for i, (train_idx, test_idx) in enumerate(
        purged_walk_forward_splits(df, n_splits=6, horizon=5, embargo=10)
    ):
        X_tr = X.iloc[train_idx]
        ...
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Iterator


def purged_walk_forward_splits(
    df:       pd.DataFrame,
    n_splits: int = 6,
    horizon:  int = 5,
    embargo:  int = 10,
    min_train_size: float = 0.50,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """
    Generador de splits (train_idx, test_idx) para walk-forward purged CV.

    Args:
        df:             DataFrame con índice temporal ordenado.
        n_splits:       Número de folds (ventanas de test).
        horizon:        Días del horizonte de predicción (para purging).
        embargo:        Días de buffer entre train y test (embargo).
        min_train_size: Fracción mínima del total usada para el primer train.

    Yields:
        (train_indices, test_indices) como arrays de posición (iloc).
    """
    n = len(df)
    # Tamaño de cada ventana de test
    test_size = int(n * (1 - min_train_size) / n_splits)
    if test_size < 1:
        test_size = max(1, n // (n_splits + 2))

    for fold in range(n_splits):
        # Test: ventana deslizante
        test_end   = n - fold * test_size
        test_start = test_end - test_size
        if test_start < 0:
            break

        # Train: todo lo anterior al test, con purging + embargo
        purge_end  = test_start           # primer día del test
        train_end  = purge_end - embargo  # embargo gap
        if train_end <= 0:
            continue

        # Purging: eliminar las últimas `horizon` filas de train
        # (sus labels se solapan con el test)
        train_end_purged = train_end - horizon
        if train_end_purged <= 10:
            continue

        train_idx = np.arange(0, train_end_purged)
        test_idx  = np.arange(test_start, test_end)

        yield train_idx, test_idx


def compute_embargo_size(n: int, pct: float = 0.01) -> int:
    """Tamaño del embargo como porcentaje del dataset (López de Prado recomienda 1%)."""
    return max(1, int(n * pct))


def deflated_sharpe_ratio(
    sharpe_obs:   float,
    n_trials:     int,
    n_obs:        int,
    skewness:     float = 0.0,
    kurtosis:     float = 3.0,
) -> float:
    """
    Deflated Sharpe Ratio (DSR) — Bailey & López de Prado (2014).

    Corrige el Sharpe Ratio por la multiplicidad de estrategias evaluadas.
    Si DSR < 0, la estrategia probablemente no tiene edge real.

    Args:
        sharpe_obs:  SR observado (anualizado)
        n_trials:    Número de configuraciones / estrategias probadas
        n_obs:       Número de observaciones en el test
        skewness:    Skewness de los retornos
        kurtosis:    Kurtosis (3 = normal)

    Returns:
        DSR en escala z (0-1 aprox). >0.95 = evidencia fuerte.
    """
    from scipy import stats

    if n_trials <= 1:
        return float(stats.norm.cdf(sharpe_obs))

    # Máximo SR esperado por azar entre n_trials ensayos
    sr_max = (
        (1 - 0.5772156649)  # Euler–Mascheroni
        * np.sqrt(np.log(n_trials))
        + 0.5772156649 / np.sqrt(np.log(n_trials))
    )

    # Varianza del SR estimado
    var_sr = (
        1 / n_obs
        * (1 + 0.5 * sharpe_obs**2
           - skewness * sharpe_obs
           + (kurtosis - 3) / 4 * sharpe_obs**2)
    )

    dsr = stats.norm.cdf(
        (sharpe_obs - sr_max) / np.sqrt(var_sr + 1e-12)
    )
    return float(dsr)
