from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.magnitude import (
    compute_expected_return, realized_vol_30d,
)


def _seed_vol(tmp_path: Path, sym: str, vol_pct: float = 0.02):
    import numpy as np
    np.random.seed(42)
    p = 100.0
    rows = []
    for i in range(35):
        ret = np.random.normal(0.0, vol_pct)
        p = p * (1 + ret)
        rows.append({
            "timestamp": 1700000000000 + i * 86400 * 1000,
            "open": p, "high": p * 1.01, "low": p * 0.99,
            "close": p, "volume": 1000,
        })
    write_ohlcv(tmp_path, sym, "1d", pd.DataFrame(rows))


def test_realized_vol_30d_positive(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.03)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    vol = realized_vol_30d(fetcher, sym)
    assert vol > 0.005


def test_expected_return_bullish_when_direction_positive(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=0.8, regime="BULL")
    assert r > 0


def test_expected_return_bearish_when_direction_negative(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=-0.8, regime="CHOP")
    assert r < 0


def test_expected_return_smaller_when_signal_weak(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r_weak = compute_expected_return(fetcher, sym, direction_raw=0.2, regime="CHOP")
    r_strong = compute_expected_return(fetcher, sym, direction_raw=0.8, regime="CHOP")
    assert abs(r_weak) < abs(r_strong)


def test_expected_return_zero_when_no_history(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=0.5, regime="CHOP")
    assert r == 0.0
