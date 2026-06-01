from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher


@pytest.fixture
def history_with_bars(tmp_path: Path) -> Path:
    df = pd.DataFrame([
        {"timestamp": 1717286400000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
        {"timestamp": 1717290000000, "open": 100, "high": 101, "low": 99,
         "close": 101, "volume": 500},
        {"timestamp": 1717293600000, "open": 101, "high": 102, "low": 100,
         "close": 102, "volume": 500},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    return tmp_path


def test_fetcher_returns_bars_strictly_before_asof(history_with_bars: Path):
    # asof = second bar timestamp; only the first bar must be returned
    asof = datetime.fromtimestamp(1717290000000 / 1000, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=10)
    assert len(df) == 1
    assert df.iloc[0]["timestamp"] == 1717286400000


def test_fetcher_respects_lookback(history_with_bars: Path):
    asof = datetime.fromtimestamp(1717293600000 / 1000 + 1, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=2)
    assert len(df) == 2
    # The two MOST RECENT bars before asof
    assert df.iloc[-1]["close"] == 102


def test_fetcher_raises_on_future_query(history_with_bars: Path):
    asof = datetime.fromtimestamp(1717290000000 / 1000, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    # Even though caller might do something silly, the public API
    # must guard against returning anything >= asof.
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=100)
    assert (df["timestamp"] < int(asof.timestamp() * 1000)).all()
