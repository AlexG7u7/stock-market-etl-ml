"""Tests de integración de features en SuperModel."""
from __future__ import annotations

import pytest

from src.ml.super_model import EXTENDED_FEATURE_COLS, INTRADAY_FEATURE_COLS, _INTRADAY_AVAILABLE


class TestSuperModelFeatureCols:
    def test_extended_includes_intraday_when_available(self):
        if not _INTRADAY_AVAILABLE or not INTRADAY_FEATURE_COLS:
            pytest.skip("intraday_features no disponible en este entorno")

        for col in INTRADAY_FEATURE_COLS:
            assert col in EXTENDED_FEATURE_COLS, f"falta {col} en EXTENDED_FEATURE_COLS"

    def test_intraday_cols_non_empty_when_module_present(self):
        if not _INTRADAY_AVAILABLE:
            pytest.skip("intraday_features no importable")

        assert len(INTRADAY_FEATURE_COLS) >= 1
        assert all(c.startswith("id_") for c in INTRADAY_FEATURE_COLS)
