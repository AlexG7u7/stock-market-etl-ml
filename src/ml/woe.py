"""
WoE (Weight of Evidence) e Information Value para features de mercado BMV.

WoE(bin_k) = ln( P(X=k | Y=1) / P(X=k | Y=0) )

IV = Σ_k [ P(X=k|Y=1) - P(X=k|Y=0) ] × WoE(k)

Interpretación del IV:
    < 0.02   → inútil
    0.02–0.1 → señal débil
    0.1–0.3  → señal media
    0.3–0.5  → señal fuerte
    > 0.5    → sospechosamente fuerte (posible look-ahead o data leak)

El WoE también sirve como transformación de feature antes de regresión logística:
hacer X* = WoE(bin(X)) linealiza la relación, maneja no-linealidades y missing
values, y produce coeficientes directamente interpretables como log-odds.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ─── Dataclasses de resultado ─────────────────────────────────────────────────

@dataclass
class BinStats:
    """Estadísticas de un bin individual."""
    bin_label:    str
    lo:           float
    hi:           float
    n:            int
    n_events:     int
    n_nonevents:  int
    event_rate:   float   # P(Y=1 | en este bin)
    pct_events:   float   # P(X=bin | Y=1)
    pct_nonevents: float  # P(X=bin | Y=0)
    woe:          float
    iv_contrib:   float   # contribución al IV total


@dataclass
class FeatureWoE:
    """Resultado WoE completo para un feature."""
    feature:  str
    iv:       float
    n_bins:   int
    bins:     list[BinStats] = field(default_factory=list)
    monotone: bool = False   # ¿los WoE son monótonos? (deseable)

    @property
    def strength(self) -> str:
        if self.iv < 0.02:   return "inútil"
        if self.iv < 0.1:    return "débil"
        if self.iv < 0.3:    return "media"
        if self.iv < 0.5:    return "fuerte"
        return "muy fuerte"

    def transform(self, x: pd.Series) -> pd.Series:
        """Aplica la transformación WoE a una serie de valores."""
        result = pd.Series(np.nan, index=x.index)
        for b in self.bins:
            mask = (x >= b.lo) & (x < b.hi)
            result[mask] = b.woe
        # Último bin incluye el valor máximo
        if self.bins:
            result[x == self.bins[-1].hi] = self.bins[-1].woe
        return result


# ─── Función principal ────────────────────────────────────────────────────────

def compute_woe(
    X: pd.Series,
    y: pd.Series,
    n_bins: int = 8,
    min_bin_pct: float = 0.02,
) -> FeatureWoE:
    """
    Calcula WoE e IV para un feature continuo X y target binario y.

    Parameters
    ----------
    X : pd.Series   — feature continuo (puede tener NaN)
    y : pd.Series   — target binario {0, 1} alineado con X
    n_bins : int    — número de bins de cuantil
    min_bin_pct : float — tamaño mínimo de bin como fracción del total

    Returns
    -------
    FeatureWoE con bins, WoE por bin, IV total.
    """
    # Alinear y limpiar
    df = pd.DataFrame({"x": X, "y": y}).dropna()
    if len(df) < 50:
        return FeatureWoE(feature=X.name or "?", iv=0.0, n_bins=0)

    total_events    = int((df["y"] == 1).sum())
    total_nonevents = int((df["y"] == 0).sum())

    if total_events == 0 or total_nonevents == 0:
        return FeatureWoE(feature=X.name or "?", iv=0.0, n_bins=0)

    # Crear bins por cuantil (igual frecuencia)
    quantiles = np.linspace(0, 100, n_bins + 1)
    breakpoints = np.unique(np.percentile(df["x"], quantiles))

    # Si hay muy pocos breakpoints únicos (feature casi constante)
    if len(breakpoints) < 3:
        return FeatureWoE(feature=X.name or "?", iv=0.0, n_bins=0)

    df["bin"] = pd.cut(df["x"], bins=breakpoints, include_lowest=True, labels=False)
    df["bin"] = df["bin"].fillna(len(breakpoints) - 2)  # outliers al último bin

    bins: list[BinStats] = []
    iv_total = 0.0

    for b_idx in sorted(df["bin"].dropna().unique()):
        sub = df[df["bin"] == b_idx]
        n_e  = int((sub["y"] == 1).sum())
        n_ne = int((sub["y"] == 0).sum())
        n_b  = len(sub)

        if n_b / len(df) < min_bin_pct:
            continue
        if n_e == 0 or n_ne == 0:
            # Sumar 0.5 para evitar log(0) — ajuste de Laplace mínimo
            n_e  = max(n_e,  0.5)
            n_ne = max(n_ne, 0.5)

        pct_e  = n_e  / total_events
        pct_ne = n_ne / total_nonevents

        woe       = float(np.log(pct_e / pct_ne))
        iv_contrib = float((pct_e - pct_ne) * woe)
        iv_total  += iv_contrib

        lo = float(breakpoints[int(b_idx)])
        hi = float(breakpoints[int(b_idx) + 1])

        bins.append(BinStats(
            bin_label   = f"[{lo:.2f}, {hi:.2f})",
            lo          = lo,
            hi          = hi,
            n           = int(n_b),
            n_events    = int(n_e),
            n_nonevents = int(n_ne),
            event_rate  = float(n_e / n_b),
            pct_events  = float(pct_e),
            pct_nonevents = float(pct_ne),
            woe         = woe,
            iv_contrib  = iv_contrib,
        ))

    # Detectar monotonía
    woes = [b.woe for b in bins]
    monotone = (
        all(woes[i] <= woes[i+1] for i in range(len(woes)-1)) or
        all(woes[i] >= woes[i+1] for i in range(len(woes)-1))
    )

    return FeatureWoE(
        feature  = str(X.name) if X.name else "?",
        iv       = round(iv_total, 5),
        n_bins   = len(bins),
        bins     = bins,
        monotone = monotone,
    )


def compute_all_woe(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "y",
    n_bins: int = 8,
) -> dict[str, FeatureWoE]:
    """
    Calcula WoE para todos los features listados.

    Returns
    -------
    Dict feature_name → FeatureWoE, ordenado por IV descendente.
    """
    results: dict[str, FeatureWoE] = {}

    for feat in feature_cols:
        if feat not in df.columns:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fw = compute_woe(df[feat], df[target_col], n_bins=n_bins)
            fw.feature = feat
        results[feat] = fw

    return dict(sorted(results.items(), key=lambda kv: kv[1].iv, reverse=True))


def woe_transform(
    df: pd.DataFrame,
    woe_map: dict[str, FeatureWoE],
) -> pd.DataFrame:
    """
    Transforma todas las columnas del DataFrame usando el mapa WoE calculado.
    Los features transformados se nombran <feature>_woe.

    Parameters
    ----------
    df      : DataFrame con los features originales
    woe_map : resultado de compute_all_woe

    Returns
    -------
    df con columnas adicionales <feat>_woe
    """
    out = df.copy()
    for feat, fw in woe_map.items():
        if feat in out.columns and fw.n_bins > 0:
            out[f"{feat}_woe"] = fw.transform(out[feat])
    return out


def iv_summary(woe_map: dict[str, FeatureWoE]) -> pd.DataFrame:
    """Tabla resumen de IV por feature, ordenada descendente."""
    rows = []
    for feat, fw in woe_map.items():
        rows.append({
            "feature":   feat,
            "iv":        fw.iv,
            "strength":  fw.strength,
            "n_bins":    fw.n_bins,
            "monotone":  fw.monotone,
        })
    return pd.DataFrame(rows).sort_values("iv", ascending=False).reset_index(drop=True)
