"""Unit tests for intel_bridge.poller — whale + news insert helpers."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from crypto_predictor.intel_bridge.fetchers import (
    StubNewsFetcher,
    StubWhaleFetcher,
)
from crypto_predictor.intel_bridge.poller import poll_news, poll_whales


def test_poll_whales_empty_fetcher_returns_zero():
    conn = MagicMock()
    n = poll_whales(conn, StubWhaleFetcher())
    assert n == 0


def test_poll_news_empty_fetcher_returns_zero():
    conn = MagicMock()
    n = poll_news(conn, StubNewsFetcher())
    assert n == 0


def test_poll_whales_inserts_returned_events():
    class _F:
        def fetch_recent(self, *, since):
            return [{
                "chain": "ethereum",
                "symbol": "BTC",
                "tx_hash": "0xabc",
                "amount_usd": 1_000_000.0,
                "from_label": "Binance",
                "to_label": "Unknown",
                "ts": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
                "raw_json": {"raw": "data"},
            }]

    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.rowcount = 1
    n = poll_whales(conn, _F())
    assert n == 1
    # Verify INSERT contained ON CONFLICT DO NOTHING
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO whale_txs" in sql
    assert "ON CONFLICT" in sql


def test_poll_news_inserts_returned_events():
    class _F:
        def fetch_recent(self, *, since):
            return [{
                "category": "hack",
                "severity": "high",
                "title": "Test breach",
                "url": "https://example.com",
                "source": "test",
                "symbols_mentioned": ["BTC"],
                "sentiment": -0.5,
                "ts": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
                "raw_json": {},
            }]

    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.rowcount = 1
    n = poll_news(conn, _F())
    assert n == 1
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO news_feed" in sql


def test_poll_whales_skips_conflict_rows():
    """If rowcount is 0 (ON CONFLICT skipped the insert), no count."""
    class _F:
        def fetch_recent(self, *, since):
            return [{
                "chain": "ethereum",
                "tx_hash": "0xdup",
                "amount_usd": 500_000.0,
                "ts": datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
                "raw_json": {},
            }]

    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.rowcount = 0  # conflict skip
    n = poll_whales(conn, _F())
    assert n == 0


def test_poll_news_dedupes_within_batch():
    """Two events with identical (source, url, ts) collapse to one insert."""
    ts = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    dup = {
        "category": "hack",
        "severity": "high",
        "title": "Same story",
        "url": "https://example.com/x",
        "source": "test",
        "symbols_mentioned": ["BTC"],
        "sentiment": -0.5,
        "ts": ts,
        "raw_json": {},
    }

    class _F:
        def fetch_recent(self, *, since):
            return [dup, dict(dup)]  # two identical events

    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.rowcount = 1
    n = poll_news(conn, _F())
    # cur.execute should have been called only once (dedup'd to a single row)
    assert cur.execute.call_count == 1
    assert n == 1
