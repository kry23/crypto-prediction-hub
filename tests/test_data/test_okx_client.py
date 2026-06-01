from unittest.mock import MagicMock

import pandas as pd
import pytest

from crypto_predictor.data.okx_client import fetch_ohlcv_paged
from crypto_predictor.data.okx_client import (
    fetch_funding_history, fetch_oi_history,
    fetch_long_short_ratio, fetch_liquidations,
)
from crypto_predictor.data.okx_client import (
    ccxt_to_okx_instid, ccxt_to_base_ccy, ccxt_to_okx_uly,
)


def test_ccxt_to_okx_instid_unified_input():
    assert ccxt_to_okx_instid("BTC/USDT:USDT") == "BTC-USDT-SWAP"


def test_ccxt_to_okx_instid_native_input_unchanged():
    assert ccxt_to_okx_instid("BTC-USDT-SWAP") == "BTC-USDT-SWAP"


def test_ccxt_to_base_ccy_unified():
    assert ccxt_to_base_ccy("BTC/USDT:USDT") == "BTC"


def test_ccxt_to_base_ccy_native():
    assert ccxt_to_base_ccy("BTC-USDT-SWAP") == "BTC"


def test_ccxt_to_okx_uly_unified():
    assert ccxt_to_okx_uly("BTC/USDT:USDT") == "BTC-USDT"


def test_ccxt_to_okx_uly_native_swap():
    assert ccxt_to_okx_uly("BTC-USDT-SWAP") == "BTC-USDT"


def test_fetch_long_short_ratio_handles_array_row_shape():
    """OKX returns rows as [ts_str, ratio_str] arrays, not dicts."""
    fake_http = MagicMock()
    fake_http.get.return_value.json.return_value = {
        "data": [
            ["1717286400000", "1.23"],
            ["1717290000000", "1.45"],
        ]
    }
    fake_http.get.return_value.status_code = 200
    df = fetch_long_short_ratio(fake_http, "BTC/USDT:USDT",
                                period="5m", limit=100)
    assert list(df.columns) == ["timestamp", "ls_ratio"]
    assert len(df) == 2
    assert df.iloc[0]["ls_ratio"] == 1.23


def test_fetch_ohlcv_paged_returns_dataframe():
    fake_ccxt = MagicMock()
    # Each fetch_ohlcv returns 3 bars then empty (end of history)
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100.0, 105.0, 99.0, 104.0, 1000.0],
         [1717290000000, 104.0, 106.0, 103.0, 105.0, 1100.0],
         [1717293600000, 105.0, 107.0, 104.0, 106.0, 1200.0]],
        [],
    ]
    df = fetch_ohlcv_paged(fake_ccxt, "BTC-USDT-SWAP", "1h",
                           since_ms=1717286400000, limit_per_page=3)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df.iloc[0]["close"] == 104.0


def test_fetch_ohlcv_paged_handles_empty_first_response():
    fake_ccxt = MagicMock()
    fake_ccxt.fetch_ohlcv.return_value = []
    df = fetch_ohlcv_paged(fake_ccxt, "BTC-USDT-SWAP", "1h",
                           since_ms=1717286400000)
    assert df.empty
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_fetch_funding_history_returns_dataframe():
    fake = MagicMock()
    fake.fetch_funding_rate_history.return_value = [
        {"timestamp": 1717286400000, "fundingRate": 0.0001},
        {"timestamp": 1717312800000, "fundingRate": -0.0002},
    ]
    df = fetch_funding_history(fake, "BTC-USDT-SWAP",
                               since_ms=1717286400000, limit=100)
    assert list(df.columns) == ["timestamp", "funding_rate"]
    assert len(df) == 2
    assert df.iloc[0]["funding_rate"] == 0.0001


def test_fetch_oi_history_returns_dataframe():
    fake = MagicMock()
    fake.fetch_open_interest_history.return_value = [
        {"timestamp": 1717286400000, "openInterestAmount": 12345.0},
        {"timestamp": 1717290000000, "openInterestAmount": 12500.0},
    ]
    df = fetch_oi_history(fake, "BTC-USDT-SWAP",
                          since_ms=1717286400000)
    assert list(df.columns) == ["timestamp", "open_interest"]
    assert len(df) == 2


def test_fetch_long_short_ratio_via_public_api(monkeypatch):
    fake_http = MagicMock()
    fake_http.get.return_value.json.return_value = {
        "data": [
            {"ts": "1717286400000", "longShortRatio": "1.23"},
            {"ts": "1717290000000", "longShortRatio": "1.45"},
        ]
    }
    fake_http.get.return_value.status_code = 200
    df = fetch_long_short_ratio(fake_http, "BTC-USDT-SWAP",
                                period="5m", limit=100)
    assert list(df.columns) == ["timestamp", "ls_ratio"]
    assert len(df) == 2
    assert df.iloc[0]["ls_ratio"] == 1.23


def test_fetch_liquidations_returns_dataframe():
    fake_http = MagicMock()
    fake_http.get.return_value.json.return_value = {
        "data": [{
            "details": [
                {"ts": "1717286400000", "side": "buy", "sz": "1.5", "bkPx": "100"},
                {"ts": "1717286500000", "side": "sell", "sz": "0.5", "bkPx": "101"},
            ]
        }]
    }
    fake_http.get.return_value.status_code = 200
    df = fetch_liquidations(fake_http, "BTC-USDT-SWAP",
                            since_ms=1717286400000)
    assert {"timestamp", "side", "size_usdt"}.issubset(df.columns)
    assert len(df) == 2
