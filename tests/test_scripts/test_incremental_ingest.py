# tests/test_scripts/test_incremental_ingest.py
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv, read_ohlcv
from scripts.incremental_ingest import (
    incremental_symbol_timeframe, since_ms_for_incremental,
)


def test_since_ms_uses_last_parquet_timestamp(tmp_path: Path):
    df = pd.DataFrame([
        {"timestamp": 1700000000000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 1000},
        {"timestamp": 1700003600000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 1000},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    since = since_ms_for_incremental(tmp_path, "BTC-USDT-SWAP", "1h",
                                      fallback_days=30)
    # Should be last timestamp + 1ms
    assert since == 1700003600001


def test_since_ms_falls_back_when_no_parquet(tmp_path: Path):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    since = since_ms_for_incremental(tmp_path, "UNKNOWN", "1h",
                                      fallback_days=7)
    # Should be ~7 days ago
    expected = now_ms - 7 * 86400 * 1000
    assert abs(since - expected) < 60 * 1000  # within 60s tolerance


def test_incremental_symbol_timeframe_appends_new_bars(tmp_path: Path):
    # Seed with one existing bar
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", pd.DataFrame([
        {"timestamp": 1700000000000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 1000},
    ]))
    fake_client = MagicMock()
    fake_client.fetch_ohlcv.side_effect = [
        [[1700003600000, 101, 102, 100, 101, 1100],
         [1700007200000, 101, 103, 100, 102, 1200]],
        [],
    ]
    n = incremental_symbol_timeframe(
        client=fake_client, root=tmp_path,
        symbol="BTC-USDT-SWAP", timeframe="1h",
        fallback_days=30,
    )
    assert n == 2
    out = read_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h")
    assert len(out) == 3
