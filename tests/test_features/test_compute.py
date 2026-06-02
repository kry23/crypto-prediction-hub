from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _seed_minimal_history(root: Path, symbol: str) -> None:
    df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 3600 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100 + (i % 5) * 0.1, "volume": 1000}
        for i in range(3000)
    ])
    write_ohlcv(root, symbol, "1h", df)
    for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
        n = max(60, 90 * (3600 // step) if step <= 3600 else 90 * (86400 // step))
        d = pd.DataFrame([
            {"timestamp": 1700000000000 + i * step * 1000, "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000}
            for i in range(n)
        ])
        write_ohlcv(root, symbol, tf, d)
    # empty futures parquets so fetcher returns empty frames cleanly
    for kind in ["funding", "oi", "ls_ratio", "liq"]:
        p = parquet_path(root, symbol, kind, "futures")
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_parquet(p, index=False)


def test_compute_features_returns_full_30_feature_dict(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_minimal_history(tmp_path, sym)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("btc:\n  - BTC-USDT-SWAP\n")
    asof = datetime.fromtimestamp(
        (1700000000000 + 2900 * 3600 * 1000) / 1000, tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)

    feats = compute_features(
        fetcher=fetcher,
        symbol=sym,
        sentiment_cache=tmp_path / "sentiment_cache.db",
        global_cache=tmp_path / "global_cache.db",
        sector_map_path=sector_map,
        mcap_rank=1,
    )
    expected_keys = {
        # momentum (6)
        "ret_15m_z", "ret_1h_z", "ret_4h_z", "ret_24h_z", "ret_7d_z",
        "mom_consistency",
        # perp (9)
        "funding_z", "funding_extreme", "oi_growth_24h", "oi_growth_z",
        "ls_ratio", "ls_ratio_change_4h", "taker_buy_sell_1h",
        "liq_pressure_long_4h", "liq_pressure_short_4h",
        # volume (1, rest deferred)
        "vol_z_24h",
        # technical (6)
        "rsi_14_1h", "rsi_overbought", "rsi_oversold", "macd_hist_1h",
        "bb_position_1h", "price_vs_sma50",
        # sentiment (4)
        "news_sent_24h", "social_sent_24h", "sent_velocity", "news_volume_z",
        # global (5)
        "btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z",
        "sector_strength_24h", "coin_btc_corr_30d",
        # meta (1)
        "mcap_rank_weight",
    }
    assert expected_keys.issubset(set(feats.keys())), \
        f"missing: {expected_keys - set(feats.keys())}"


def test_compute_features_under_500ms(tmp_path: Path):
    import time
    sym = "BTC-USDT-SWAP"
    _seed_minimal_history(tmp_path, sym)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("btc:\n  - BTC-USDT-SWAP\n")
    asof = datetime.fromtimestamp(
        (1700000000000 + 2900 * 3600 * 1000) / 1000, tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    t0 = time.perf_counter()
    compute_features(
        fetcher=fetcher, symbol=sym,
        sentiment_cache=tmp_path / "sentiment_cache.db",
        global_cache=tmp_path / "global_cache.db",
        sector_map_path=sector_map,
        mcap_rank=1,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500, f"too slow: {elapsed_ms:.0f}ms"
