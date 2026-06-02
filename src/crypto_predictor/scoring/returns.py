"""Actual return helpers used by validation and backtest."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from crypto_predictor.data.parquet_store import read_ohlcv


def actual_return(*, root: Path, symbol: str,
                  start_time: datetime, horizon_hours: int) -> float | None:
    """Compute log return between two bars `horizon_hours` apart, starting at start_time.

    Returns None if either the start bar or end bar is missing.
    """
    df = read_ohlcv(root, symbol, "1h")
    if df.empty:
        return None
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int((start_time + timedelta(hours=horizon_hours)).timestamp() * 1000)
    # Tolerance: accept bars within ±1 hour of target
    tol = 3600 * 1000
    start_row = df[(df["timestamp"] >= start_ms - tol) &
                   (df["timestamp"] <= start_ms + tol)]
    end_row = df[(df["timestamp"] >= end_ms - tol) &
                 (df["timestamp"] <= end_ms + tol)]
    if start_row.empty or end_row.empty:
        return None
    p0 = float(start_row["close"].iloc[0])
    p1 = float(end_row["close"].iloc[-1])
    if p0 <= 0 or p1 <= 0:
        return None
    return math.log(p1 / p0)
