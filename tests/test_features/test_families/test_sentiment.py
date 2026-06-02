from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.families.sentiment import (
    compute_sentiment_features, write_sentiment_cache,
)
from crypto_predictor.features.fetcher import FeatureFetcher


def test_sentiment_returns_neutral_when_cache_empty(tmp_path: Path):
    cache = tmp_path / "sentiment_cache.db"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_sentiment_features(fetcher, "BTC-USDT-SWAP",
                                        cache_db=cache)
    assert feats["news_sent_24h"] == 0.0
    assert feats["social_sent_24h"] == 0.0
    assert feats["sent_velocity"] == 0.0
    assert feats["news_volume_z"] == 0.0


def test_sentiment_reads_from_cache_when_present(tmp_path: Path):
    cache = tmp_path / "sentiment_cache.db"
    asof = datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc)
    write_sentiment_cache(cache, "BTC-USDT-SWAP",
                          asof.isoformat(),
                          news_sent_24h=0.42,
                          social_sent_24h=0.18,
                          sent_velocity=0.05,
                          news_volume_z=1.2)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_sentiment_features(fetcher, "BTC-USDT-SWAP",
                                        cache_db=cache)
    assert feats["news_sent_24h"] == pytest.approx(0.42)
    assert feats["social_sent_24h"] == pytest.approx(0.18)
    assert feats["news_volume_z"] == pytest.approx(1.2)
