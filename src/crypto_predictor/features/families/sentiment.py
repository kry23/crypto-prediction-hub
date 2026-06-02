"""Family 5 — sentiment. Reads from sentiment_cache.db (filled by Week 7 fetcher)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from crypto_predictor.features.fetcher import FeatureFetcher

NEUTRAL = {
    "news_sent_24h": 0.0,
    "social_sent_24h": 0.0,
    "sent_velocity": 0.0,
    "news_volume_z": 0.0,
}

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_cache (
    symbol           TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    news_sent_24h    REAL,
    social_sent_24h  REAL,
    sent_velocity    REAL,
    news_volume_z    REAL,
    PRIMARY KEY (symbol, timestamp)
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)
    conn.commit()


def write_sentiment_cache(db: Path, symbol: str, timestamp: str,
                          *, news_sent_24h: float, social_sent_24h: float,
                          sent_velocity: float, news_volume_z: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO sentiment_cache VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, timestamp, news_sent_24h, social_sent_24h,
             sent_velocity, news_volume_z),
        )
        conn.commit()
    finally:
        conn.close()


def compute_sentiment_features(fetcher: FeatureFetcher, symbol: str,
                               *, cache_db: Path) -> dict[str, float]:
    """Read pre-cached sentiment for (symbol, asof). Returns neutral if missing."""
    if not cache_db.exists():
        return dict(NEUTRAL)
    conn = sqlite3.connect(str(cache_db))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT news_sent_24h, social_sent_24h, sent_velocity, news_volume_z "
            "FROM sentiment_cache "
            "WHERE symbol = ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, fetcher.asof.isoformat()),
        ).fetchone()
        if row is None:
            return dict(NEUTRAL)
        return {
            "news_sent_24h": row[0] or 0.0,
            "social_sent_24h": row[1] or 0.0,
            "sent_velocity": row[2] or 0.0,
            "news_volume_z": row[3] or 0.0,
        }
    finally:
        conn.close()
