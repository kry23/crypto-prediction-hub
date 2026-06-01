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


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_funding_history(client, symbol: str, since_ms: int,
                          limit: int = 100) -> pd.DataFrame:
    """Fetch funding rate history for a perp via ccxt."""
    rows = client.fetch_funding_rate_history(symbol, since=since_ms, limit=limit)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "funding_rate"])
    df = pd.DataFrame([
        {"timestamp": r["timestamp"], "funding_rate": r["fundingRate"]}
        for r in rows
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_oi_history(client, symbol: str, since_ms: int,
                     limit: int = 100) -> pd.DataFrame:
    """Fetch open interest history for a perp via ccxt."""
    rows = client.fetch_open_interest_history(symbol, since=since_ms, limit=limit)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open_interest"])
    df = pd.DataFrame([
        {"timestamp": r["timestamp"], "open_interest": r["openInterestAmount"]}
        for r in rows
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_long_short_ratio(http_client, symbol: str, *,
                           period: str = "5m", limit: int = 100) -> pd.DataFrame:
    """Fetch L/S account ratio from OKX public API.

    http_client must be an httpx.Client-like object with .get returning a Response
    whose .json() yields {"data": [{"ts": str, "longShortRatio": str}, ...]}.
    """
    url = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
    params = {"ccy": symbol.split("-")[0], "period": period, "limit": limit}
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("ls_ratio_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    data = resp.json().get("data", [])
    if not data:
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    df = pd.DataFrame([
        {"timestamp": int(r["ts"]), "ls_ratio": float(r["longShortRatio"])}
        for r in data
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_liquidations(http_client, symbol: str, since_ms: int) -> pd.DataFrame:
    """Fetch liquidation events from OKX public API."""
    url = "https://www.okx.com/api/v5/public/liquidation-orders"
    params = {"instType": "SWAP", "instId": symbol, "before": str(since_ms)}
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("liquidations_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    blocks = resp.json().get("data", [])
    rows = []
    for blk in blocks:
        for d in blk.get("details", []):
            size_usdt = float(d["sz"]) * float(d["bkPx"])
            rows.append({
                "timestamp": int(d["ts"]),
                "side": d["side"],
                "size_usdt": size_usdt,
            })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
