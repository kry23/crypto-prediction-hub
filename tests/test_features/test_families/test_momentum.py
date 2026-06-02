from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.momentum import compute_momentum_features
from crypto_predictor.features.fetcher import FeatureFetcher


def make_synthetic_1h_bars(n: int, start_ms: int, start_price: float = 100.0,
                           drift_per_bar: float = 0.001) -> pd.DataFrame:
    rows = []
    p = start_price
    for i in range(n):
        rows.append({
            "timestamp": start_ms + i * 3600 * 1000,
            "open": p,
            "high": p * 1.005,
            "low": p * 0.995,
            "close": p * (1 + drift_per_bar),
            "volume": 1000,
        })
        p = p * (1 + drift_per_bar)
    return pd.DataFrame(rows)


def test_momentum_features_returns_expected_keys(tmp_path: Path):
    df = make_synthetic_1h_bars(n=2200, start_ms=1700000000000)  # ~3 months
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    # Also need 15m and 1d (Family uses 15m and daily). Reuse 1h reshape for test.
    df_15m = make_synthetic_1h_bars(n=8800, start_ms=1700000000000,
                                    drift_per_bar=0.00025)
    df_15m["timestamp"] = 1700000000000 + (df_15m.index * 900 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "15m", df_15m)
    df_4h = make_synthetic_1h_bars(n=550, start_ms=1700000000000,
                                   drift_per_bar=0.004)
    df_4h["timestamp"] = 1700000000000 + (df_4h.index * 14400 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "4h", df_4h)
    df_1d = make_synthetic_1h_bars(n=100, start_ms=1700000000000,
                                   drift_per_bar=0.024)
    df_1d["timestamp"] = 1700000000000 + (df_1d.index * 86400 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1d", df_1d)

    asof = datetime.fromtimestamp((1700000000000 + 90 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_momentum_features(fetcher, "BTC-USDT-SWAP")
    expected = {"ret_15m_z", "ret_1h_z", "ret_4h_z", "ret_24h_z",
                "ret_7d_z", "mom_consistency"}
    assert expected.issubset(set(feats.keys()))


def test_momentum_consistency_in_unit_range(tmp_path: Path):
    df = make_synthetic_1h_bars(n=2200, start_ms=1700000000000,
                                drift_per_bar=0.001)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    asof = datetime.fromtimestamp((1700000000000 + 90 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_momentum_features(fetcher, "BTC-USDT-SWAP")
    assert 0.0 <= feats["mom_consistency"] <= 1.0
