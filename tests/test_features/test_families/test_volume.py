from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.volume import compute_volume_features
from crypto_predictor.features.fetcher import FeatureFetcher


def test_volume_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 86400 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100, "volume": 1000 + i}
        for i in range(40)
    ])
    write_ohlcv(tmp_path, sym, "1d", df)
    asof = datetime.fromtimestamp((1700000000000 + 41 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_volume_features(fetcher, sym)
    expected = {"vol_z_24h"}
    assert expected.issubset(set(feats.keys()))


def test_vol_z_24h_positive_when_spike(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    rows = [
        {"timestamp": 1700000000000 + i * 86400 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100, "volume": 1000}
        for i in range(30)
    ]
    rows.append({"timestamp": 1700000000000 + 30 * 86400 * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 10_000})
    write_ohlcv(tmp_path, sym, "1d", pd.DataFrame(rows))
    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_volume_features(fetcher, sym)
    assert feats["vol_z_24h"] > 3.0
