"""Poller helpers — convert fetcher output into idempotent PG inserts.

Both pollers are safe to call repeatedly: whale_txs has UNIQUE(chain, tx_hash)
so duplicates skip; news_feed has no natural key so we de-dupe in Python
by (source, url, ts) before inserting (best effort)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger(__name__)


_WHALE_INSERT_SQL = """
    INSERT INTO whale_txs (
        chain, symbol, tx_hash, amount_usd, from_label, to_label, ts, raw_json
    ) VALUES (
        %(chain)s, %(symbol)s, %(tx_hash)s, %(amount_usd)s,
        %(from_label)s, %(to_label)s, %(ts)s, %(raw_json)s
    )
    ON CONFLICT (chain, tx_hash) DO NOTHING
"""


_NEWS_INSERT_SQL = """
    INSERT INTO news_feed (
        category, severity, title, url, source,
        symbols_mentioned, sentiment, ts, raw_json
    ) VALUES (
        %(category)s, %(severity)s, %(title)s, %(url)s, %(source)s,
        %(symbols_mentioned)s, %(sentiment)s, %(ts)s, %(raw_json)s
    )
"""


def _since(lookback_hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=lookback_hours)


def poll_whales(conn, fetcher, *, lookback_hours: int = 24) -> int:
    """Run the fetcher; INSERT new whale_txs rows; return count inserted.

    Idempotency: whale_txs has UNIQUE(chain, tx_hash); duplicate inserts
    are silently dropped via ON CONFLICT DO NOTHING. We sum rowcount per
    execute() call to get the true number of new rows.
    """
    since = _since(lookback_hours)
    events = fetcher.fetch_recent(since=since)
    if not events:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for ev in events:
            params = {
                "chain": ev["chain"],
                "symbol": ev.get("symbol"),
                "tx_hash": ev["tx_hash"],
                "amount_usd": ev.get("amount_usd"),
                "from_label": ev.get("from_label"),
                "to_label": ev.get("to_label"),
                "ts": ev["ts"],
                "raw_json": json.dumps(ev.get("raw_json", {})),
            }
            cur.execute(_WHALE_INSERT_SQL, params)
            # rowcount is 1 on insert, 0 on conflict-skip
            if cur.rowcount and cur.rowcount > 0:
                inserted += cur.rowcount
    conn.commit()
    log.info("poll_whales_done", fetched=len(events), inserted=inserted)
    return inserted


def _news_dedup_key(ev: dict) -> tuple:
    """Best-effort de-dupe key for news events within a single poll batch."""
    return (ev.get("source"), ev.get("url"), ev.get("ts"))


def poll_news(conn, fetcher, *, lookback_hours: int = 24) -> int:
    """Run the fetcher; INSERT new news_feed rows; return count inserted.

    news_feed has no natural unique key (the UI/spec accepts duplicate
    titles across sources), so we de-dupe in-process by
    (source, url, ts) before inserting. Cross-batch dedup is a Day-14
    follow-up — for v1.0 a small re-insert is acceptable.
    """
    since = _since(lookback_hours)
    events = fetcher.fetch_recent(since=since)
    if not events:
        return 0

    # In-batch dedup
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for ev in events:
        key = _news_dedup_key(ev)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)

    inserted = 0
    with conn.cursor() as cur:
        for ev in deduped:
            params = {
                "category": ev["category"],
                "severity": ev["severity"],
                "title": ev["title"],
                "url": ev.get("url"),
                "source": ev.get("source"),
                "symbols_mentioned": ev.get("symbols_mentioned") or [],
                "sentiment": ev.get("sentiment"),
                "ts": ev["ts"],
                "raw_json": json.dumps(ev.get("raw_json", {})),
            }
            cur.execute(_NEWS_INSERT_SQL, params)
            if cur.rowcount and cur.rowcount > 0:
                inserted += cur.rowcount
    conn.commit()
    log.info("poll_news_done",
             fetched=len(events), deduped=len(deduped), inserted=inserted)
    return inserted
