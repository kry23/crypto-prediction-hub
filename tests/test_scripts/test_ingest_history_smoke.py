from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from scripts.ingest_history import ingest_symbol_ohlcv


def test_ingest_symbol_ohlcv_writes_parquet(tmp_path: Path):
    fake_ccxt = MagicMock()
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100, 101, 99, 100, 500],
         [1717290000000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt,
        root=tmp_path,
        symbol="BTC-USDT-SWAP",
        timeframe="1h",
        since_ms=1717286400000,
    )
    out = pd.read_parquet(tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet")
    assert len(out) == 2


def test_ingest_symbol_ohlcv_is_resumable(tmp_path: Path):
    fake_ccxt = MagicMock()
    # First run
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt, root=tmp_path, symbol="BTC-USDT-SWAP",
        timeframe="1h", since_ms=1717286400000,
    )
    # Second run with new data
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717290000000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt, root=tmp_path, symbol="BTC-USDT-SWAP",
        timeframe="1h", since_ms=1717286400000,
    )
    out = pd.read_parquet(tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet")
    assert len(out) == 2  # both rows present, no dup
