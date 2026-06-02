"""Thin ccxt wrapper for OKX with paging + retry."""
from __future__ import annotations

import time

import pandas as pd
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def ccxt_to_okx_instid(symbol: str) -> str:
    """Map ccxt unified perp symbol to OKX native instId.

    'BTC/USDT:USDT' -> 'BTC-USDT-SWAP'
    'BTC-USDT-SWAP' -> 'BTC-USDT-SWAP' (already native, returned unchanged)
    """
    if "/" not in symbol and ":" not in symbol:
        return symbol  # already native
    base, rest = symbol.split("/", 1)
    quote, _, settle = rest.partition(":")
    return f"{base}-{quote}-SWAP"


def ccxt_to_base_ccy(symbol: str) -> str:
    """Extract base currency code from any supported symbol format.

    'BTC/USDT:USDT' -> 'BTC'
    'BTC-USDT-SWAP' -> 'BTC'
    'BTCUSDT'        -> 'BTCUSDT' (best effort, no separator found)
    """
    for sep in ("/", "-"):
        if sep in symbol:
            return symbol.split(sep)[0]
    return symbol


def ccxt_to_okx_uly(symbol: str) -> str:
    """Map any supported perp symbol to OKX `uly` (underlying) format.

    'BTC/USDT:USDT' -> 'BTC-USDT'
    'BTC-USDT-SWAP' -> 'BTC-USDT'
    'BTC-USDT'       -> 'BTC-USDT' (already uly)
    """
    instid = ccxt_to_okx_instid(symbol)
    # instid is now BASE-QUOTE-SWAP or already native; strip the -SWAP suffix
    if instid.endswith("-SWAP"):
        return instid[: -len("-SWAP")]
    return instid


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


def _extract_oi_value(row: dict) -> float | None:
    """Extract OI numeric value from a ccxt fetch_open_interest_history row.

    OKX populates `openInterestValue` (notional in USD) and leaves
    `openInterestAmount` as null for many timeframes. As a fallback, the
    raw OKX response in `info` is `[ts, oi_value, volume]`.
    Returns None when no usable numeric value is found.
    """
    for key in ("openInterestValue", "openInterestAmount", "openInterest"):
        v = row.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        # Treat NaN as missing
        if f != f:  # noqa: PLR0124  (NaN check)
            continue
        return f
    info = row.get("info")
    # OKX raw: list/tuple [ts, oi_value, volume]
    if isinstance(info, (list, tuple)) and len(info) >= 2:
        try:
            f = float(info[1])
            if f == f:
                return f
        except (TypeError, ValueError):
            pass
    # Some exchanges return info as dict
    if isinstance(info, dict):
        for key in ("oi", "openInterest", "openInterestValue",
                    "openInterestAmount"):
            v = info.get(key)
            if v is None:
                continue
            try:
                f = float(v)
                if f == f:
                    return f
            except (TypeError, ValueError):
                continue
    return None


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_oi_history(client, symbol: str, since_ms: int,
                     limit: int = 100) -> pd.DataFrame:
    """Fetch open interest history for a perp via ccxt.

    Rows where no usable OI value can be extracted are skipped, so the
    returned DataFrame never contains null open_interest values.
    """
    rows = client.fetch_open_interest_history(symbol, since=since_ms, limit=limit)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open_interest"])
    parsed: list[dict] = []
    for r in rows:
        ts = r.get("timestamp")
        if ts is None:
            continue
        oi = _extract_oi_value(r)
        if oi is None:
            continue
        parsed.append({"timestamp": int(ts), "open_interest": oi})
    if not parsed:
        return pd.DataFrame(columns=["timestamp", "open_interest"])
    df = pd.DataFrame(parsed)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_long_short_ratio(http_client, symbol: str, *,
                           period: str = "5m", limit: int = 100) -> pd.DataFrame:
    """Fetch L/S account ratio from OKX public API.

    http_client must be an httpx.Client-like object with .get returning a Response
    whose .json() yields {"data": [{"ts": str, "longShortRatio": str}, ...]}.
    """
    url = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
    params = {"ccy": ccxt_to_base_ccy(symbol), "period": period, "limit": limit}
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("ls_ratio_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    data = resp.json().get("data", [])
    if not data:
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    # OKX returns rows in either of two shapes depending on endpoint variant:
    #   - list/tuple: [ts_str, ratio_str]
    #   - dict:       {"ts": ts_str, "longShortRatio": ratio_str}
    rows = []
    for r in data:
        if isinstance(r, dict):
            ts = r.get("ts")
            ratio = r.get("longShortRatio") or r.get("ratio")
        else:  # list/tuple
            ts, ratio = r[0], r[1]
        rows.append({"timestamp": int(ts), "ls_ratio": float(ratio)})
    df = pd.DataFrame(rows)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_liquidations(http_client, symbol: str, since_ms: int) -> pd.DataFrame:
    """Fetch liquidation events from OKX public API."""
    url = "https://www.okx.com/api/v5/public/liquidation-orders"
    # OKX public liquidation-orders requires `uly` (e.g. BTC-USDT) for SWAP,
    # not `instId`. `state=filled` is also required.
    params = {
        "instType": "SWAP",
        "uly": ccxt_to_okx_uly(symbol),
        "state": "filled",
        "before": str(since_ms),
    }
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("liquidations_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    blocks = resp.json().get("data", [])
    rows = []
    for blk in blocks:
        for d in blk.get("details", []):
            try:
                sz = float(d.get("sz") or 0)
                bk_px = float(d.get("bkPx") or 0)
            except (TypeError, ValueError):
                continue
            size_usdt = sz * bk_px
            rows.append({
                "timestamp": int(d["ts"]),
                "side": d["side"],
                "size_usdt": size_usdt,
            })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
