from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.technical import compute_technical_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _make_bars(n: int, start_ms: int = 1700000000000) -> pd.DataFrame:
    return pd.DataFrame([
        {"timestamp": start_ms + i * 3600 * 1000, "open": 100 + i * 0.1,
         "high": 101 + i * 0.1, "low": 99 + i * 0.1, "close": 100 + i * 0.1,
         "volume": 1000}
        for i in range(n)
    ])


def test_technical_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(200))
    asof = datetime.fromtimestamp((1700000000000 + 250 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    expected = {"rsi_14_1h", "rsi_overbought", "rsi_oversold", "macd_hist_1h",
                "bb_position_1h", "price_vs_sma50"}
    assert expected.issubset(set(feats.keys()))


def test_rsi_is_in_range(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(200))
    asof = datetime.fromtimestamp((1700000000000 + 250 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    assert 0 <= feats["rsi_14_1h"] <= 100


def test_bb_position_in_unit_range_for_uptrend(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(100))
    asof = datetime.fromtimestamp((1700000000000 + 150 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    assert -0.5 <= feats["bb_position_1h"] <= 1.5
