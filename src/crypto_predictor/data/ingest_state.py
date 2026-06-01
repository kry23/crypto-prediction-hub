"""Compute the next `since` cursor for resumable ingest."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.data.parquet_store import read_ohlcv


def next_since_ms_for_ohlcv(root: Path, symbol: str, timeframe: str,
                            *, default_since_ms: int) -> int:
    """Return the timestamp from which ingest should resume.

    If parquet exists, return last_timestamp + 1. Otherwise return default.
    """
    existing = read_ohlcv(root, symbol, timeframe)
    if existing.empty:
        return default_since_ms
    return int(existing["timestamp"].max()) + 1
