"""Bulk-ingest 6 months of OKX-Global perp data into parquet.

Run once at project setup. Idempotent + resumable. Wall-clock ~6 hours
due to OKX rate limits.

Usage:
    python scripts/ingest_history.py --root data/history --months 6
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import httpx
import structlog

from crypto_predictor.data.ingest_state import next_since_ms_for_ohlcv
from crypto_predictor.data.okx_client import (
    fetch_funding_history,
    fetch_liquidations,
    fetch_long_short_ratio,
    fetch_ohlcv_paged,
    fetch_oi_history,
)
from crypto_predictor.data.parquet_store import (
    append_ohlcv,
    parquet_path,
)
from crypto_predictor.logging_config import configure_logging

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

log = structlog.get_logger(__name__)


def ingest_symbol_ohlcv(client, root: Path, symbol: str, timeframe: str,
                        since_ms: int) -> int:
    """Ingest OHLCV for one (symbol, timeframe). Returns row count written."""
    cursor = next_since_ms_for_ohlcv(root, symbol, timeframe,
                                     default_since_ms=since_ms)
    df = fetch_ohlcv_paged(client, symbol, timeframe, cursor)
    if df.empty:
        return 0
    append_ohlcv(root, symbol, timeframe, df)
    return len(df)


def ingest_symbol_futures(ccxt_client, http_client, root: Path,
                          symbol: str, since_ms: int) -> dict[str, int]:
    """Ingest funding + OI + L/S + liquidations for one symbol."""
    counts = {}

    # Funding
    fpath = parquet_path(root, symbol, "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    f_df = fetch_funding_history(ccxt_client, symbol, since_ms)
    if not f_df.empty:
        f_df.to_parquet(fpath, index=False)
    counts["funding"] = len(f_df)

    # OI
    oi_df = fetch_oi_history(ccxt_client, symbol, since_ms)
    oipath = parquet_path(root, symbol, "oi", "futures")
    oipath.parent.mkdir(parents=True, exist_ok=True)
    if not oi_df.empty:
        oi_df.to_parquet(oipath, index=False)
    counts["oi"] = len(oi_df)

    # L/S ratio
    ls_df = fetch_long_short_ratio(http_client, symbol, period="5m", limit=500)
    lspath = parquet_path(root, symbol, "ls_ratio", "futures")
    lspath.parent.mkdir(parents=True, exist_ok=True)
    if not ls_df.empty:
        ls_df.to_parquet(lspath, index=False)
    counts["ls_ratio"] = len(ls_df)

    # Liquidations
    liq_df = fetch_liquidations(http_client, symbol, since_ms)
    liqpath = parquet_path(root, symbol, "liq", "futures")
    liqpath.parent.mkdir(parents=True, exist_ok=True)
    if not liq_df.empty:
        liq_df.to_parquet(liqpath, index=False)
    counts["liq"] = len(liq_df)

    return counts


def list_okx_perps(client) -> list[str]:
    """Return list of active USDT-margined perpetual symbols on OKX."""
    markets = client.load_markets()
    return [
        m["symbol"] for m in markets.values()
        if m.get("swap") and m.get("settle") == "USDT" and m.get("active")
    ]


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True,
                        help="Output root, e.g. data/history")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--limit-symbols", type=int, default=None,
                        help="For testing: ingest only first N symbols")
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)

    okx = ccxt.okx({"enableRateLimit": True})
    http = httpx.Client(timeout=30.0)

    since_dt = datetime.now(timezone.utc).timestamp() * 1000 - args.months * 30 * 86400 * 1000
    since_ms = int(since_dt)

    symbols = list_okx_perps(okx)
    if args.limit_symbols:
        symbols = symbols[:args.limit_symbols]
    log.info("ingest_start", n_symbols=len(symbols), months=args.months)

    for i, sym in enumerate(symbols, start=1):
        try:
            for tf in TIMEFRAMES:
                n = ingest_symbol_ohlcv(okx, args.root, sym, tf, since_ms)
                log.info("ohlcv_done", symbol=sym, timeframe=tf, rows=n,
                         progress=f"{i}/{len(symbols)}")
            counts = ingest_symbol_futures(okx, http, args.root, sym, since_ms)
            log.info("futures_done", symbol=sym, **counts)
        except Exception as exc:  # pragma: no cover
            log.error("symbol_failed", symbol=sym, error=str(exc))
        time.sleep(0.25)

    log.info("ingest_complete", n_symbols=len(symbols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
