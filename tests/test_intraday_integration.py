"""Tests for intraday feature integration."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.features import (
    FEATURE_COLS,
    get_all_feature_cols,
    add_intraday_features_to_panel,
)
from src.ml.intraday_features import (
    INTRADAY_COLS,
    INTRADAY_FEATURE_COLS,
    _day_features,
    add_intraday_features,
    compute_intraday_cs_medians,
)


def _synthetic_bars(
    n: int = 24,
    start_price: float = 100.0,
    step: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """24 barras 5m (~2h) con drift alcista y volumen constante."""
    prices = start_price + np.arange(n, dtype=float) * step
    volumes = np.full(n, 1000.0)
    return prices, volumes


def test_day_features_synthetic_5m_bars() -> None:
    prices, volumes = _synthetic_bars(n=24, start_price=100.0, step=0.5)
    feats = _day_features(
        prices,
        volumes=volumes,
        prev_close=99.0,
        vol_avg_20d=20_000.0,
    )
    assert feats is not None
    assert feats["id_ret"] > 0
    assert 0.0 <= feats["id_close_loc"] <= 1.0
    assert feats["id_up_frac"] == pytest.approx(1.0)
    assert feats["id_gap"] == pytest.approx((100.0 - 99.0) / 99.0 * 100, rel=1e-3)
    assert feats["id_vol_ratio"] == pytest.approx(1.2)


def test_day_features_too_few_bars_returns_none() -> None:
    prices = np.array([100.0, 100.5, 101.0, 101.5, 102.0])
    assert _day_features(prices) is None


def test_get_all_feature_cols_include_intraday() -> None:
    base = get_all_feature_cols()
    with_id = get_all_feature_cols(include_intraday=True)
    assert len(with_id) == len(FEATURE_COLS) + len(INTRADAY_FEATURE_COLS)
    for col in INTRADAY_FEATURE_COLS:
        assert col in with_id
        assert col not in base


def test_intraday_feature_cols_export() -> None:
    assert INTRADAY_FEATURE_COLS == INTRADAY_COLS
    assert "id_vol_ratio" in INTRADAY_FEATURE_COLS
    assert "id_gap" in INTRADAY_FEATURE_COLS


def test_imputation_ffill_then_cs_median(tmp_path, monkeypatch) -> None:
    """Forward-fill intra-ticker; NaN restantes → mediana cross-seccional."""
    from src.ml import intraday_features as idf_mod

    intraday_dir = tmp_path / "intraday"
    intraday_dir.mkdir()
    monkeypatch.setattr(idf_mod, "INTRADAY_DIR", intraday_dir)

    bars = []
    for day, (op, vol) in enumerate([(100.0, 5000.0), (102.0, 8000.0)], start=1):
        for i in range(12):
            ts = pd.Timestamp(f"2025-01-{day:02d} 09:{i * 5:02d}:00")
            bars.append({"datetime": ts, "price": op + i * 0.2, "volume": vol})
    pd.DataFrame(bars).to_parquet(intraday_dir / "TEST.parquet", index=False)

    idx = pd.date_range("2025-01-01", periods=5, freq="D")
    panel_a = pd.DataFrame(index=idx)
    panel_b = pd.DataFrame(index=idx)

    cs_medians = {
        "id_ret": 0.5, "id_range": 1.0, "id_close_loc": 0.5,
        "id_rvol": 0.3, "id_last_hr": 0.1, "id_first_hr": 0.1,
        "id_up_frac": 0.5, "id_pm_am": 0.0, "id_vol_ratio": 1.0,
        "id_gap": 0.0,
    }

    out_a = add_intraday_features(panel_a, "TEST", cs_medians=cs_medians)
    out_b = add_intraday_features(panel_b, "MISSING", cs_medians=cs_medians)

    assert out_a.loc["2025-01-03", "id_ret"] == pytest.approx(out_a.loc["2025-01-02", "id_ret"])
    assert out_b["id_ret"].notna().all()
    assert out_b.loc[idx[0], "id_ret"] == pytest.approx(0.5)

    medians = compute_intraday_cs_medians({"A": out_a, "B": out_b})
    assert "id_ret" in medians
    assert np.isfinite(medians["id_ret"])


def test_add_intraday_features_to_panel_wrapper(tmp_path, monkeypatch) -> None:
    from src.ml import intraday_features as idf_mod

    intraday_dir = tmp_path / "intraday"
    intraday_dir.mkdir()
    monkeypatch.setattr(idf_mod, "INTRADAY_DIR", intraday_dir)

    rows = []
    for i in range(8):
        rows.append({
            "datetime": pd.Timestamp(f"2025-02-01 09:{i * 5:02d}:00"),
            "price": 50.0 + i * 0.1,
        })
    pd.DataFrame(rows).to_parquet(intraday_dir / "WRP.parquet", index=False)

    df = pd.DataFrame(index=pd.date_range("2025-02-01", periods=1))
    out = add_intraday_features_to_panel("WRP", df)
    for col in INTRADAY_FEATURE_COLS:
        assert col in out.columns
