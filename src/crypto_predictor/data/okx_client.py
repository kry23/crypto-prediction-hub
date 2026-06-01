"""Thin ccxt wrapper for OKX with paging + retry."""
from __future__ import annotations

import time

import pandas as pd
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


@retry(stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=1, min=1, max=30))
def _fetch_with_retry(client, symbol: str, timeframe: str,
                      since: int, limit: int) -> list:
    return client.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)


def fetch_ohlcv_paged(
    client,
    symbol: str,
    timeframe: str,
    since_ms: int,
    *,
    limit_per_page: int = 300,
    max_pages: int = 100,
    sleep_between_ms: int = 250,
) -> pd.DataFrame:
    """Fetch OHLCV bars from `since_ms` onward, paging until exhausted.

    Returns a DataFrame with columns [timestamp, open, high, low, close, volume].
    timestamp is integer epoch-ms; conversion to datetime is downstream concern.
    """
    rows: list[list] = []
    cursor = since_ms
    for _ in range(max_pages):
        batch = _fetch_with_retry(client, symbol, timeframe, cursor, limit_per_page)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if len(batch) < limit_per_page:
            break
        cursor = last_ts + 1
        time.sleep(sleep_between_ms / 1000.0)
    if not rows:
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df
