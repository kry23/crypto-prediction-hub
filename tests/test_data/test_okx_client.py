from unittest.mock import MagicMock

import pandas as pd
import pytest

from crypto_predictor.data.okx_client import fetch_ohlcv_paged


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
