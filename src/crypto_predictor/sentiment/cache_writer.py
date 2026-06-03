"""Persist sentiment features into sentiment_cache.db."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.features.families.sentiment import write_sentiment_cache


def write_sentiment_for_symbol(*, db: Path, symbol: str, timestamp: str,
                                news_sent_24h: float, social_sent_24h: float,
                                sent_velocity: float, news_volume_z: float) -> None:
    """Thin pass-through to Plan A's `write_sentiment_cache` for orchestration tidiness."""
    write_sentiment_cache(
        db=db, symbol=symbol, timestamp=timestamp,
        news_sent_24h=news_sent_24h, social_sent_24h=social_sent_24h,
        sent_velocity=sent_velocity, news_volume_z=news_volume_z,
    )
