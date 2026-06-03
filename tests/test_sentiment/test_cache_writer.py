from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.families.sentiment import compute_sentiment_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.sentiment.cache_writer import write_sentiment_for_symbol


def test_write_sentiment_round_trips(tmp_path: Path):
    cache_db = tmp_path / "sentiment_cache.db"
    asof = datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc)
    write_sentiment_for_symbol(
        db=cache_db, symbol="BTC/USDT:USDT", timestamp=asof.isoformat(),
        news_sent_24h=0.42, social_sent_24h=0.18,
        sent_velocity=0.05, news_volume_z=1.2,
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_sentiment_features(fetcher, "BTC/USDT:USDT",
                                        cache_db=cache_db)
    assert abs(feats["news_sent_24h"] - 0.42) < 1e-6
