"""
Pipeline de producción: Ensemble primario + Meta-labeling.

Combina:
  1. EnsembleModel calibrado (decide dirección)
  2. Triple-barrier labels (alinea target con stops/targets reales)
  3. MetaModel (decide si la señal vale la pena)

Expone `train_pipeline()` que ambos scripts (generate_signals, simulate_week)
pueden usar, y `ProductionModel` que envuelve ambos modelos para predicción.

Uso:
    from src.ml.pipeline import train_pipeline

    model = train_pipeline(feat_frames, raw_data, feature_cols)
    result = model.predict(last_row_df, feature_cols)
    # result["p_primary"], result["p_meta"], result["take"] (bool)
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.ml.ensemble   import EnsembleModel
from src.ml.meta_model import MetaModel
from src.ml.labeling   import triple_barrier_labels, sample_uniqueness_weights

warnings.filterwarnings("ignore")

HORIZON       = 5
MULT_TARGET   = 1.5
MULT_STOP     = 1.5
META_QUANTILE = 0.60   # selectividad del meta (toma top 40% de confianza)
MARKET_MA     = 20     # ventana de la media móvil para el filtro de régimen


def market_is_riskon(naftrac: pd.DataFrame | None, ma_window: int = MARKET_MA) -> bool:
    """
    ¿El mercado (NAFTRAC) está 'risk-on'? = precio sobre su media móvil.

    Filtro probado en backtest: operar largos solo con el índice en tendencia
    redujo el drawdown a la mitad y casi eliminó las pérdidas del período.

    Returns True si no hay datos (no filtra), para no bloquear por error.
    """
    if naftrac is None or "Close" not in naftrac.columns or len(naftrac) < ma_window:
        return True
    close = naftrac["Close"]
    ma = close.rolling(ma_window).mean().iloc[-1]
    return bool(close.iloc[-1] >= ma)


class ProductionModel:
    """Envuelve el modelo primario + meta para predicción conjunta."""

    def __init__(self, primary: EnsembleModel, meta: MetaModel | None,
                 feature_cols: list[str], meta_cut: float, primary_thresh: float = 0.53):
        self.primary        = primary
        self.meta           = meta
        self.feature_cols   = feature_cols
        self.meta_cut       = meta_cut
        self.primary_thresh = primary_thresh

    def predict(self, df: pd.DataFrame) -> dict:
        """
        Predice para cada fila de df.
        Returns dict con arrays: p_primary, p_meta, take (bool).
        """
        p_primary = self.primary.predict_proba(df, self.feature_cols)
        if self.meta is not None:
            p_meta = self.meta.predict_proba(df, self.feature_cols, primary_proba=p_primary)
        else:
            p_meta = np.full(len(df), np.nan)

        take = p_primary >= self.primary_thresh
        if self.meta is not None:
            take = take & (p_meta >= self.meta_cut)

        return {"p_primary": p_primary, "p_meta": p_meta, "take": take}

    def predict_one(self, row_df: pd.DataFrame) -> dict:
        """Predice para una sola fila. Returns dict con floats escalares."""
        r = self.predict(row_df)
        return {
            "p_primary": float(r["p_primary"][0]),
            "p_meta":    float(r["p_meta"][0]) if not np.isnan(r["p_meta"][0]) else None,
            "take":      bool(r["take"][0]),
        }


def train_pipeline(
    feat_frames:  dict[str, pd.DataFrame],
    raw_data:     dict[str, pd.DataFrame],
    feature_cols: list[str],
    target_col:   str = "y",
    primary_thresh: float = 0.53,
    use_meta:     bool = True,
    top_features: int = 15,
) -> ProductionModel:
    """
    Entrena el pipeline completo (primario + meta) sobre feat_frames.

    Args:
        feat_frames:  dict ticker → DataFrame con features (incluye cross-section).
                      Debe tener `target_col` ya calculado.
        raw_data:     dict ticker → OHLCV crudo (para triple-barrier labels).
        feature_cols: lista de features.
        target_col:   columna target binaria.
        primary_thresh: umbral del modelo primario.
        use_meta:     si False, solo entrena el primario.
        top_features: features a usar en el ensemble.

    Returns:
        ProductionModel listo para predecir.
    """
    # ── 1. Dataset de entrenamiento del primario ──────────────────────────────
    rows = []
    for name, feat in feat_frames.items():
        avail = [c for c in feature_cols if c in feat.columns]
        clean = feat.dropna(subset=avail + [target_col])
        if len(clean) > 30:
            rows.append(clean)
    if not rows:
        raise RuntimeError("Sin datos para entrenar el pipeline")

    train = pd.concat(rows).sort_index()

    primary = EnsembleModel(top_features=top_features, calibrate=True)
    primary.fit(train, feature_cols=feature_cols, target_col=target_col)

    if not use_meta:
        return ProductionModel(primary, None, feature_cols, meta_cut=0.0,
                               primary_thresh=primary_thresh)

    # ── 2. Triple-barrier labels para el meta-modelo ──────────────────────────
    meta_frames = []
    for name, feat in feat_frames.items():
        raw = raw_data.get(name)
        if raw is None:
            continue
        try:
            vol = (feat["atr_pct"] / 100.0) if "atr_pct" in feat.columns else \
                  raw["Close"].pct_change().rolling(14).std()
            # Alinear vol al índice de feat
            tb = triple_barrier_labels(
                close=raw["Close"].reindex(feat.index),
                high=raw["High"].reindex(feat.index),
                low=raw["Low"].reindex(feat.index),
                vol=vol, horizon=HORIZON,
                mult_target=MULT_TARGET, mult_stop=MULT_STOP,
            )
            f2 = feat.copy()
            f2["meta_y"]   = tb["label"]
            f2["tb_bars"]  = tb["bars"]
            meta_frames.append(f2)
        except Exception:
            continue

    meta = None
    meta_cut = 0.0
    if meta_frames:
        meta_train = pd.concat(meta_frames).sort_index()
        avail = [c for c in feature_cols if c in meta_train.columns]
        meta_train = meta_train.dropna(subset=avail + ["meta_y"])

        if len(meta_train) > 100 and meta_train["meta_y"].nunique() > 1:
            p_primary_tr = primary.predict_proba(meta_train, feature_cols)
            w = sample_uniqueness_weights(meta_train["tb_bars"], horizon=HORIZON)

            meta = MetaModel()
            meta.fit(
                meta_train, feature_cols=feature_cols,
                primary_proba=p_primary_tr,
                meta_label=meta_train["meta_y"].values,
                sample_weight=w.values,
            )

            # Umbral del meta = percentil sobre los candidatos primarios
            mask = p_primary_tr >= primary_thresh
            p_meta_tr = meta.predict_proba(meta_train, feature_cols, primary_proba=p_primary_tr)
            if mask.sum() > 20:
                meta_cut = float(np.quantile(p_meta_tr[mask], META_QUANTILE))
            else:
                meta_cut = float(np.quantile(p_meta_tr, META_QUANTILE))

    return ProductionModel(primary, meta, feature_cols, meta_cut=meta_cut,
                           primary_thresh=primary_thresh)
