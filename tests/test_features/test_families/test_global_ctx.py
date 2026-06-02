from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.families.global_ctx import (
    compute_global_features, write_global_cache,
)
from crypto_predictor.features.fetcher import FeatureFetcher


def test_global_returns_neutral_when_cache_empty(tmp_path: Path):
    cache = tmp_path / "global_cache.db"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_global_features(fetcher, "BTC-USDT-SWAP",
                                     cache_db=cache)
    for k in ["btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z",
              "sector_strength_24h", "coin_btc_corr_30d"]:
        assert feats[k] == 0.0


def test_global_reads_from_cache_when_present(tmp_path: Path):
    cache = tmp_path / "global_cache.db"
    asof = datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc)
    write_global_cache(cache, asof.isoformat(),
                       btc_dom_trend_7d=0.012,
                       eth_btc_trend_7d=-0.005,
                       total_mcap_z=1.4,
                       sector_btc=0.02, sector_eth=0.03,
                       sector_defi=-0.01, sector_l1=0.0)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_global_features(fetcher, "BTC-USDT-SWAP",
                                     cache_db=cache, sector="btc")
    assert feats["btc_dom_trend_7d"] == pytest.approx(0.012)
    assert feats["sector_strength_24h"] == pytest.approx(0.02)
