from pathlib import Path

import pandas as pd

from crypto_predictor.data.ingest_state import next_since_ms_for_ohlcv


def test_returns_default_when_no_existing_parquet(tmp_path: Path):
    default = 1700000000000
    since = next_since_ms_for_ohlcv(tmp_path, "ABCUSDT", "1h", default_since_ms=default)
    assert since == default


def test_returns_last_timestamp_plus_one_when_parquet_exists(tmp_path: Path):
    from crypto_predictor.data.parquet_store import write_ohlcv
    df = pd.DataFrame([
        {"timestamp": 1717286400000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
        {"timestamp": 1717290000000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
    ])
    write_ohlcv(tmp_path, "ABCUSDT", "1h", df)
    since = next_since_ms_for_ohlcv(tmp_path, "ABCUSDT", "1h", default_since_ms=0)
    assert since == 1717290000000 + 1
