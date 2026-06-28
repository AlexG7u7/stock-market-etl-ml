"""
Ising Market Model — Cellular Automaton for BMV price dynamics
==============================================================

Física estadística aplicada a mercados financieros (econofísica).
Basado en los modelos de Bouchaud, Cont, Potters y Sornette.

El mercado es una red de N×N agentes (espines de Ising) que interactúan
localmente. La dinámica emergente replica los hechos estilizados observados
en la BMV:
  - Colas gordas en la distribución de retornos (fat tails)
  - Volatility clustering (ARCH effects)
  - Transición de fase ferromagnética → burbujas y crashes
  - Criticalidad de largo alcance cerca de T_c

Modelo matemático
-----------------
  Estado: sigma_i ∈ {+1, -1}  (comprador / vendedor)

  Regla de actualización (CA sincrónica con BC periódicas):
    h_i(t) = J * sum_{j~i} sigma_j(t) + h_ext(t)
    P(sigma_i(t+1) = +1) = sigmoid(2 * h_i / T)

  Campo externo:
    h_ext(t) = alpha * r(t-1) / r_0   [retroalimentación de momento]

  Precio (formación Walrasiana):
    r(t) = lambda * M(t) + sigma_f * xi(t),   xi ~ N(0,1)
    p(t+1) = p(t) * exp(r(t))

  Magnetización (orden de mercado):
    M(t) = (1/N^2) * sum_i sigma_i(t)  ∈ [-1, +1]

Parámetros clave
----------------
  T  — temperatura (ruido / irracionalidad). T_c ≈ J para la transición.
  J  — acoplamiento (herding, efecto manada).
  lambda  — impacto de precio del desequilibrio de órdenes.
  sigma_f — ruido fundamental (noticias exógenas).

Integración con el pipeline
---------------------------
  1. Calibrar (T, J) con datos históricos BMV (máxima verosimilitud o ABC).
  2. Generar trayectorias sintéticas para aumentar datos de entrenamiento LSTM.
  3. Detectar régimen de mercado (fase) como feature adicional.
  4. Calcular señales de riesgo (volatility forecast, tail risk).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Core CA engine (NumPy — vectorizado, sin loops Python en el hot path)
# ─────────────────────────────────────────────────────────────────────────────

def _periodic_neighbor_sum(grid: NDArray[np.int8]) -> NDArray[np.float64]:
    """Suma vectorizada de 4 vecinos von Neumann con condiciones periódicas."""
    return (
        np.roll(grid, 1, axis=0) +
        np.roll(grid, -1, axis=0) +
        np.roll(grid, 1, axis=1) +
        np.roll(grid, -1, axis=1)
    ).astype(np.float64)


def step(
    grid: NDArray[np.int8],
    J: float,
    T: float,
    h_ext: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> NDArray[np.int8]:
    """
    Ejecuta un paso de tiempo del CA Ising.

    Actualización paralela (sincrónica): todos los espines se actualizan
    simultáneamente usando el estado del tiempo anterior (CA puro).

    Parameters
    ----------
    grid : NDArray[int8]  shape (N, N)  valores en {-1, +1}
    J    : acoplamiento ferromagnético (herding)
    T    : temperatura (irracionalidad/ruido)
    h_ext: campo externo uniforme (momentum precio)
    rng  : generador numpy aleatorio (reproducibilidad)

    Returns
    -------
    new_grid : NDArray[int8]  shape (N, N)
    """
    if rng is None:
        rng = np.random.default_rng()

    neighbor_sum = _periodic_neighbor_sum(grid)
    local_field = J * neighbor_sum + h_ext

    # P(sigma_i = +1) = sigmoid(2 * h_i / T)
    prob_up = 1.0 / (1.0 + np.exp(-2.0 * local_field / max(T, 1e-8)))
    u = rng.random(grid.shape)
    new_grid = np.where(u < prob_up, 1, -1).astype(np.int8)
    return new_grid


def magnetization(grid: NDArray[np.int8]) -> float:
    """M = ⟨sigma⟩ ∈ [-1, +1]. Orden de mercado: +1 = todos comprando."""
    return float(grid.mean())


def local_correlation(grid: NDArray[np.int8]) -> float:
    """Correlación local promedio (proxy de clustering espacial)."""
    ns = _periodic_neighbor_sum(grid)
    return float((grid * ns).mean()) / 4.0


# ─────────────────────────────────────────────────────────────────────────────
# Modelo completo: simulación de precio + features de mercado
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IsingMarketConfig:
    """Configuración del modelo. Calibrar con datos históricos BMV."""

    N: int = 20                # lado de la cuadrícula (N×N agentes)
    T: float = 1.1             # temperatura: cerca de T_c = J para fat tails
    J: float = 1.0             # acoplamiento ferromagnético (herding)
    lam: float = 0.025         # impacto de precio del desequilibrio
    sigma_f: float = 0.005     # ruido fundamental (noticias)
    alpha_mom: float = 0.5     # fuerza de retroalimentación de momento
    r0: float = 0.02           # retorno de referencia para normalización
    seed: Optional[int] = None


@dataclass
class SimulationResult:
    """Resultado de una trayectoria de simulación."""

    prices: NDArray[np.float64]         # serie de precios
    log_returns: NDArray[np.float64]    # retornos logarítmicos
    magnetizations: NDArray[np.float64] # M(t)
    local_corrs: NDArray[np.float64]    # correlación local espacial
    phase_labels: list[str]             # etiqueta de fase por paso

    def to_dataframe(self) -> pd.DataFrame:
        """Convierte a DataFrame para análisis / features ML."""
        n = len(self.log_returns)
        df = pd.DataFrame({
            "price": self.prices[1:],           # alineado con retornos
            "log_return": self.log_returns,
            "magnetization": self.magnetizations,
            "local_corr": self.local_corrs,
            "phase": self.phase_labels,
            "volatility_5": pd.Series(self.log_returns).rolling(5).std().values,
            "volatility_20": pd.Series(self.log_returns).rolling(20).std().values,
            "abs_return": np.abs(self.log_returns),
        })
        df["phase_encoded"] = df["phase"].map(
            {"ferromagnetic": -1, "critical": 0, "paramagnetic": 1}
        )
        return df


def classify_phase(M: float, J: float, T: float) -> str:
    """
    Clasifica el régimen de mercado basado en magnetización y parámetros.

    La transición de fase ocurre en T_c ≈ J (campo medio, red cuadrada: T_c ≈ 2.269·J).
    Tres regímenes:
      - ferromagnético: |M| > 0.5 — mercado en tendencia fuerte
      - crítico:        |M| ∈ (0.15, 0.5) — zona de transición, fat tails
      - paramagnético:  |M| < 0.15 — mercado ruidoso/eficiente
    """
    abs_M = abs(M)
    if abs_M > 0.5:
        return "ferromagnetic"
    elif abs_M > 0.15:
        return "critical"
    else:
        return "paramagnetic"


class IsingMarket:
    """
    Simulador de mercado Ising.

    Uso básico
    ----------
    >>> market = IsingMarket(IsingMarketConfig(T=1.1, J=1.0, seed=42))
    >>> result = market.simulate(n_steps=500, p0=100.0)
    >>> df = result.to_dataframe()

    Integración con datos históricos
    ---------------------------------
    >>> market.calibrate(historical_returns_series)  # estima T, J por MLE/ABC
    >>> synthetic_df = market.generate_augmented_data(1000)  # data augmentation para LSTM
    """

    def __init__(self, config: IsingMarketConfig | None = None):
        self.cfg = config or IsingMarketConfig()
        self.rng = np.random.default_rng(self.cfg.seed)
        self.grid = self._init_grid()

    def _init_grid(self) -> NDArray[np.int8]:
        return self.rng.choice([-1, 1], size=(self.cfg.N, self.cfg.N)).astype(np.int8)

    def reset(self, seed: int | None = None) -> None:
        """Reinicia la cuadrícula con nueva semilla aleatoria."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.grid = self._init_grid()

    def simulate(
        self,
        n_steps: int = 500,
        p0: float = 100.0,
        warmup: int = 50,
    ) -> SimulationResult:
        """
        Simula n_steps pasos del modelo Ising.

        Parameters
        ----------
        n_steps  : número de pasos a simular (días de trading simulados)
        p0       : precio inicial
        warmup   : pasos de calentamiento para equilibrar la red (no se guardan)

        Returns
        -------
        SimulationResult con series temporales listas para ML
        """
        cfg = self.cfg
        N2 = cfg.N ** 2

        # Calentamiento: equilibrar la red sin guardar datos
        for _ in range(warmup):
            self.grid = step(self.grid, cfg.J, cfg.T, rng=self.rng)

        prices = np.empty(n_steps + 1)
        log_returns = np.empty(n_steps)
        mags = np.empty(n_steps)
        local_corrs = np.empty(n_steps)
        phases: list[str] = []

        prices[0] = p0
        last_ret = 0.0

        for t in range(n_steps):
            # Campo externo: retroalimentación de momentum del precio
            h_ext = cfg.alpha_mom * last_ret / max(cfg.r0, 1e-8)

            self.grid = step(self.grid, cfg.J, cfg.T, h_ext=h_ext, rng=self.rng)

            M = magnetization(self.grid)
            lc = local_correlation(self.grid)
            mags[t] = M
            local_corrs[t] = lc
            phases.append(classify_phase(M, cfg.J, cfg.T))

            # Formación de precio (Walras + ruido fundamental)
            noise = self.rng.standard_normal() * cfg.sigma_f
            last_ret = cfg.lam * M + noise
            log_returns[t] = last_ret
            prices[t + 1] = prices[t] * np.exp(last_ret)

        logger.info(
            "Simulación completada: %d pasos, precio final %.4f, "
            "volatilidad %.4f%%",
            n_steps,
            prices[-1],
            log_returns.std() * 100,
        )

        return SimulationResult(
            prices=prices,
            log_returns=log_returns,
            magnetizations=mags,
            local_corrs=local_corrs,
            phase_labels=phases,
        )

    def calibrate(self, returns: pd.Series, method: str = "moment") -> None:
        """
        Calibra los parámetros (T, J) usando datos históricos de retornos BMV.

        Método 'moment': matching de momentos empírico.
          - sigma_empirica → calibra lambda y sigma_f
          - kurtosis_exceso → proxy de temperatura (T ≈ J / kurtosis_signal)
          - autocorr abs retornos → proxy de herding J

        En producción, usar ABC (Approximate Bayesian Computation) o SMM.

        Parameters
        ----------
        returns : pd.Series de retornos logarítmicos históricos (BMV ticker)
        method  : "moment" (rápido) | "abc" (lento, más preciso, no implementado aún)
        """
        if method != "moment":
            raise NotImplementedError("Solo 'moment' implementado. ABC en roadmap.")

        std_emp = float(returns.std())
        kurtosis_exc = float(returns.kurtosis())   # exceso de curtosis
        autocorr_abs = float(returns.abs().autocorr(lag=1))

        # Heurísticas de calibración por matching de momentos
        # sigma_f ≈ std del proceso fundamental (ruido bajo J=0, T→∞)
        self.cfg.sigma_f = max(std_emp * 0.3, 0.001)

        # lambda calibrado para que la escala de precio sea correcta
        # Bajo fase crítica, std ≈ lambda * std(M) + sigma_f
        # std(M) ≈ 0.15 en fase crítica típica → lambda ≈ (std_emp - sigma_f) / 0.15
        self.cfg.lam = max((std_emp - self.cfg.sigma_f) / 0.15, 0.01)

        # Temperatura: kurtosis > 0 sugiere criticidad (T ≈ J)
        # Aumentar T si kurtosis es baja (más eficiente)
        if kurtosis_exc > 5:
            self.cfg.T = 1.0   # muy cercano a T_c, fat tails
        elif kurtosis_exc > 2:
            self.cfg.T = 1.3   # algo crítico
        else:
            self.cfg.T = 2.5   # más eficiente

        # Herding J ≈ f(autocorrelación de retornos absolutos)
        # Mayor autocorr → mayor herding
        self.cfg.J = 1.0 + autocorr_abs * 0.8

        logger.info(
            "Calibración completada: T=%.3f, J=%.3f, lambda=%.4f, sigma_f=%.4f | "
            "Datos: std=%.4f%%, kurtosis=%.2f, autocorr_abs=%.3f",
            self.cfg.T, self.cfg.J, self.cfg.lam, self.cfg.sigma_f,
            std_emp * 100, kurtosis_exc, autocorr_abs,
        )

    def generate_augmented_data(
        self,
        n_samples: int = 1000,
        n_steps: int = 250,
        p0: float = 100.0,
    ) -> pd.DataFrame:
        """
        Genera múltiples trayectorias sintéticas para data augmentation del LSTM.

        Parameters
        ----------
        n_samples : número de trayectorias independientes
        n_steps   : longitud de cada trayectoria (días)
        p0        : precio inicial de cada trayectoria

        Returns
        -------
        DataFrame con trayectorias concatenadas + columna 'trajectory_id'
        """
        dfs = []
        for i in range(n_samples):
            self.reset(seed=self.cfg.seed + i if self.cfg.seed else None)
            result = self.simulate(n_steps=n_steps, p0=p0)
            df = result.to_dataframe()
            df["trajectory_id"] = i
            dfs.append(df)
        logger.info("Generadas %d trayectorias sintéticas (%d pasos c/u)", n_samples, n_steps)
        return pd.concat(dfs, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Features de régimen para integrar con el pipeline LSTM existente
# ─────────────────────────────────────────────────────────────────────────────

def extract_regime_features(
    prices_df: pd.DataFrame,
    price_col: str = "close",
    window_calibration: int = 252,
    window_rolling: int = 21,
) -> pd.DataFrame:
    """
    Extrae features de régimen Ising a partir de datos históricos BMV reales.

    Flujo:
      1. Calcula retornos log del precio histórico.
      2. Calibra el modelo Ising en ventana deslizante.
      3. Simula 1 paso y extrae M, fase, correlación local como features.

    Estos features se usan como input adicional al LSTM:
      - ising_phase_encoded  : régimen {-1=ferromagnético, 0=crítico, 1=paramagnético}
      - ising_magnetization  : orden de mercado simulado
      - ising_local_corr     : clustering espacial de agentes

    Parameters
    ----------
    prices_df    : DataFrame con columna de precio (e.g. de precios_historicos SQL)
    price_col    : nombre de la columna de precio de cierre
    window_calibration : días para calibrar parámetros
    window_rolling     : días para rolling de features

    Returns
    -------
    prices_df con columnas adicionales de features Ising
    """
    df = prices_df.copy()
    df["log_return"] = np.log(df[price_col] / df[price_col].shift(1))
    df = df.dropna(subset=["log_return"])

    market = IsingMarket()
    phases = []
    mags = []
    lcs = []

    for i in range(len(df)):
        if i < window_calibration:
            phases.append(None)
            mags.append(np.nan)
            lcs.append(np.nan)
            continue

        window_returns = df["log_return"].iloc[i - window_calibration:i]
        try:
            market.calibrate(window_returns)
        except Exception:
            pass

        market.reset()
        r = market.simulate(n_steps=1, warmup=20)
        M = float(r.magnetizations[0])
        mags.append(M)
        lcs.append(float(r.local_corrs[0]))
        phases.append(classify_phase(M, market.cfg.J, market.cfg.T))

    df["ising_phase"] = phases
    df["ising_magnetization"] = mags
    df["ising_local_corr"] = lcs
    df["ising_phase_encoded"] = df["ising_phase"].map(
        {"ferromagnetic": -1, "critical": 0, "paramagnetic": 1}
    )

    return df
