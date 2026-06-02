from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path
from crypto_predictor.features.families.perp import compute_perp_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _write_parquet(root: Path, symbol: str, kind: str, df: pd.DataFrame):
    p = parquet_path(root, symbol, kind, "futures")
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def test_perp_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    # 30d of 8-hour funding samples = 90 rows
    f_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000,
         "funding_rate": 0.0001 * ((-1) ** i)}
        for i in range(90)
    ])
    _write_parquet(tmp_path, sym, "funding", f_df)

    oi_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 3600 * 1000,
         "open_interest": 10000 + i * 10}
        for i in range(720)  # 30d × 24h
    ])
    _write_parquet(tmp_path, sym, "oi", oi_df)

    ls_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 300 * 1000,
         "ls_ratio": 1.0 + 0.01 * ((-1) ** i)}
        for i in range(200)
    ])
    _write_parquet(tmp_path, sym, "ls_ratio", ls_df)

    liq_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 60 * 1000,
         "side": "buy" if i % 2 else "sell",
         "size_usdt": 5000}
        for i in range(50)
    ])
    _write_parquet(tmp_path, sym, "liq", liq_df)

    # OHLCV needed by tilt logic later but compute_perp_features doesn't need it
    from crypto_predictor.data.parquet_store import write_ohlcv
    write_ohlcv(tmp_path, sym, "4h",
                pd.DataFrame([{"timestamp": 1700000000000, "open": 100,
                               "high": 101, "low": 99, "close": 100,
                               "volume": 500}]))
    # 1h bar for taker_buy_sell proxy
    write_ohlcv(tmp_path, sym, "1h",
                pd.DataFrame([{"timestamp": 1700000000000, "open": 100,
                               "high": 101, "low": 99, "close": 100.5,
                               "volume": 500}]))

    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_perp_features(fetcher, sym)
    expected = {"funding_z", "funding_extreme", "oi_growth_24h", "oi_growth_z",
                "ls_ratio", "ls_ratio_change_4h", "taker_buy_sell_1h",
                "liq_pressure_long_4h", "liq_pressure_short_4h"}
    assert expected.issubset(set(feats.keys()))


def test_funding_extreme_is_binary(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    # All-zero funding → funding_extreme=0
    f_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000, "funding_rate": 0.0}
        for i in range(90)
    ])
    _write_parquet(tmp_path, sym, "funding", f_df)
    # ensure other parquets exist as empties
    for k in ["oi", "ls_ratio", "liq"]:
        _write_parquet(tmp_path, sym, k, pd.DataFrame())
    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_perp_features(fetcher, sym)
    assert feats["funding_extreme"] in (0.0, 1.0)
