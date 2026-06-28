"""
Meta-Labeling Model (López de Prado, AFML Cap. 3).

Arquitectura de dos niveles:

  NIVEL 1 — Modelo primario (EnsembleModel):
      Decide la DIRECCIÓN. "Creo que esto sube."
      Tiene un edge pequeño pero muchos falsos positivos.

  NIVEL 2 — Meta-modelo (esta clase):
      No decide dirección. Decide CONFIANZA:
      "Dado que el primario dice comprar, ¿realmente va a funcionar?"
      Entrenado sobre triple-barrier labels (¿el trade tocó target o stop?).

      Solo se opera cuando el meta-modelo da alta probabilidad.

Ventaja:
  Mejora la PRECISIÓN (menos trades perdedores) sacrificando recall
  (menos trades en total). Ideal cuando el costo de un trade malo es alto.

Uso:
    from src.ml.meta_model import MetaModel

    meta = MetaModel()
    meta.fit(train_df, feature_cols, primary_proba=p_train, meta_label=tb_labels)

    # Decisión final: actúa solo si meta_proba alta
    meta_p = meta.predict_proba(test_df, feature_cols, primary_proba=p_test)
    actuar = meta_p >= 0.5
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, precision_score, recall_score

warnings.filterwarnings("ignore")

_META_LGBM = dict(
    objective         = "binary",
    verbosity         = -1,
    n_estimators      = 200,
    num_leaves        = 31,
    learning_rate     = 0.03,
    min_child_samples = 40,
    feature_fraction  = 0.7,
    bagging_fraction  = 0.85,
    bagging_freq      = 1,
    reg_lambda        = 5.0,
    n_jobs            = 2,
    random_state      = 42,
)


class MetaModel:
    """
    Meta-modelo que decide SI tomar la señal del modelo primario.

    Atributos tras fit():
        auc        (float): AUC del meta-modelo en validación
        precision  (float): precisión al umbral 0.5
        recall     (float): recall al umbral 0.5
        feat_imp   (DataFrame): importancia de features
    """

    def __init__(self):
        self._model    = None
        self._features = []
        self.auc       = 0.5
        self.precision = 0.0
        self.recall    = 0.0
        self.feat_imp: pd.DataFrame | None = None
        self._fitted   = False

    def _build_X(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        primary_proba: np.ndarray,
    ) -> pd.DataFrame:
        """Construye la matriz de features del meta-modelo: features + prob primaria."""
        X = df[feature_cols].copy().reset_index(drop=True)
        X["_primary_p"]      = np.asarray(primary_proba)
        # Distancia de la prob primaria al umbral (confianza)
        X["_primary_edge"]   = np.abs(np.asarray(primary_proba) - 0.5)
        return X

    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        primary_proba: np.ndarray,
        meta_label: np.ndarray,
        sample_weight: np.ndarray | None = None,
        val_ratio: float = 0.2,
    ) -> "MetaModel":
        """
        Entrena el meta-modelo.

        Args:
            df:            DataFrame con features (alineado con primary_proba).
            feature_cols:  Columnas de features.
            primary_proba: P(subida) del modelo primario para cada fila.
            meta_label:    1 si el trade realmente ganó (triple-barrier), 0 si no.
            sample_weight: Pesos de unicidad (opcional).
            val_ratio:     Fracción final para validación.
        """
        import lightgbm as lgb

        X = self._build_X(df, feature_cols, primary_proba)
        y = pd.Series(np.asarray(meta_label)).reset_index(drop=True)

        mask = X.notna().all(axis=1) & y.notna()
        X, y = X[mask], y[mask].astype(int)
        sw = None
        if sample_weight is not None:
            sw = pd.Series(np.asarray(sample_weight)).reset_index(drop=True)[mask]

        self._features = X.columns.tolist()

        n_val = int(len(X) * val_ratio)
        X_tr, X_val = X.iloc[:-n_val], X.iloc[-n_val:]
        y_tr, y_val = y.iloc[:-n_val], y.iloc[-n_val:]
        sw_tr = sw.iloc[:-n_val].values if sw is not None else None

        self._model = lgb.LGBMClassifier(**_META_LGBM)
        self._model.fit(X_tr.values, y_tr.values, sample_weight=sw_tr)

        if len(np.unique(y_val)) > 1:
            p_val = self._model.predict_proba(X_val.values)[:, 1]
            self.auc       = roc_auc_score(y_val, p_val)
            pred           = (p_val >= 0.5).astype(int)
            self.precision = precision_score(y_val, pred, zero_division=0)
            self.recall    = recall_score(y_val, pred, zero_division=0)

        self.feat_imp = pd.DataFrame({
            "feature":    self._features,
            "importance": self._model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        self._fitted = True
        return self

    def predict_proba(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        primary_proba: np.ndarray,
    ) -> np.ndarray:
        """P(la señal primaria sea correcta) para cada fila."""
        if not self._fitted:
            raise RuntimeError("Llama fit() antes de predict_proba()")
        X = self._build_X(df, feature_cols, primary_proba)[self._features].fillna(0.0)
        return self._model.predict_proba(X.values)[:, 1]

    def summary(self) -> str:
        top = ", ".join(self.feat_imp["feature"].head(4)) if self.feat_imp is not None else "?"
        return (
            "MetaModel (LightGBM sobre triple-barrier labels)\n"
            f"  AUC:        {self.auc:.4f}\n"
            f"  Precisión:  {self.precision:.4f}  (de los trades que toma, % ganadores)\n"
            f"  Recall:     {self.recall:.4f}  (% de ganadores que captura)\n"
            f"  Top feats:  {top}"
        )
