from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.returns import actual_return


def _seed_hourly(root: Path, symbol: str, n: int = 100, start_price: float = 100.0):
    rows = []
    p = start_price
    for i in range(n):
        rows.append({
            "timestamp": 1700000000000 + i * 3600 * 1000,
            "open": p, "high": p * 1.01, "low": p * 0.99,
            "close": p * 1.001, "volume": 1000,
        })
        p *= 1.001
    write_ohlcv(root, symbol, "1h", pd.DataFrame(rows))


def test_actual_return_24h_computes_log_return(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_hourly(tmp_path, sym, n=100)
    # At i=50 close = 100 * 1.001^51 ≈ 105.18
    # 24h later (i=74) close = 100 * 1.001^75 ≈ 107.74
    start = datetime.fromtimestamp(
        (1700000000000 + 50 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    # log(107.74 / 105.18) ≈ 0.024
    assert 0.020 < r < 0.030


def test_actual_return_returns_none_when_data_missing(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    start = datetime.fromtimestamp(1700000000000 / 1000, tz=timezone.utc)
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    assert r is None


def test_actual_return_returns_none_when_horizon_extends_past_data(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_hourly(tmp_path, sym, n=20)  # only 20 bars
    start = datetime.fromtimestamp(
        (1700000000000 + 10 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    # 24h horizon → need bar at i=34, but only 20 exist
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    assert r is None
