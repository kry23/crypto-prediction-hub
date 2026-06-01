from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import (
    parquet_path, write_ohlcv, read_ohlcv, append_ohlcv, safe_symbol,
)


def test_parquet_path_partitioned_by_symbol_and_timeframe(tmp_path: Path):
    p = parquet_path(tmp_path, "BTC-USDT-SWAP", "1h", "ohlcv")
    assert p == tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet"


def test_write_read_roundtrip(tmp_path: Path):
    df = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},
        {"timestamp": 2, "open": 101.0, "high": 103.0, "low": 100.0,
         "close": 102.0, "volume": 1100.0},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    out = read_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h")
    assert len(out) == 2
    assert out.iloc[0]["close"] == 101.0


def test_append_dedups_on_timestamp(tmp_path: Path):
    df1 = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},
    ])
    df2 = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},   # dup
        {"timestamp": 2, "open": 101.0, "high": 103.0, "low": 100.0,
         "close": 102.0, "volume": 1100.0},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df1)
    append_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df2)
    out = read_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h")
    assert len(out) == 2
    assert list(out["timestamp"]) == [1, 2]


def test_read_missing_returns_empty(tmp_path: Path):
    out = read_ohlcv(tmp_path, "NOPE", "1h")
    assert out.empty


def test_safe_symbol_replaces_slash_and_colon():
    assert safe_symbol("BTC/USDT:USDT") == "BTC_USDT_USDT"


def test_safe_symbol_passes_through_safe_input():
    assert safe_symbol("BTC-USDT-SWAP") == "BTC-USDT-SWAP"


def test_parquet_path_uses_safe_symbol(tmp_path: Path):
    p = parquet_path(tmp_path, "BTC/USDT:USDT", "1h", "ohlcv")
    assert p == tmp_path / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet"
