"""Tests for BMV catalog and SQL ticker sync."""
from __future__ import annotations

from src.data.bmv_catalog import (
    BMV_EMISORA_SERIE,
    BMV_YFINANCE,
    INTRADAY_MAP,
    sql_ticker_list,
)
from src.data.store import BMV_TICKERS


def test_bmv_catalog_consistency() -> None:
    assert len(BMV_YFINANCE) == 36
    assert BMV_YFINANCE.keys() == BMV_EMISORA_SERIE.keys()
    assert INTRADAY_MAP == BMV_EMISORA_SERIE
    assert BMV_TICKERS == BMV_YFINANCE


def test_sql_ticker_list_count() -> None:
    tickers = sql_ticker_list()
    assert len(tickers) == 36
    assert tickers == sorted(set(BMV_EMISORA_SERIE.values()))
