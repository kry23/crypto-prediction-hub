"""Incremental OHLCV + futures fetcher: only pulls bars since last ingest.

Runs in 1-2 min for 340-symbol universe vs 3h for full backfill.
Schedule daily at 06:15 UTC (before validate_pending at 06:30 UTC).
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

from crypto_predictor.data.okx_client import (
    fetch_funding_history, fetch_liquidations, fetch_long_short_ratio,
    fetch_ohlcv_paged, fetch_oi_history,
)
from crypto_predictor.data.parquet_store import (
    append_ohlcv, parquet_path, read_ohlcv,
)
from crypto_predictor.logging_config import configure_logging
from crypto_predictor.orchestrator.universe import list_active_perps

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

log = structlog.get_logger(__name__)


def since_ms_for_incremental(root: Path, symbol: str, timeframe: str,
                              *, fallback_days: int) -> int:
    """Cursor for incremental: last bar timestamp + 1ms, or fallback_days back if no data."""
    existing = read_ohlcv(root, symbol, timeframe)
    if existing.empty:
        return int(datetime.now(timezone.utc).timestamp() * 1000) - fallback_days * 86400 * 1000
    return int(existing["timestamp"].max()) + 1


def incremental_symbol_timeframe(*, client, root: Path,
                                  symbol: str, timeframe: str,
                                  fallback_days: int = 30) -> int:
    """Fetch bars since last existing bar; append. Returns count appended."""
    cursor = since_ms_for_incremental(root, symbol, timeframe,
                                       fallback_days=fallback_days)
    df = fetch_ohlcv_paged(client, symbol, timeframe, cursor)
    if df.empty:
        return 0
    append_ohlcv(root, symbol, timeframe, df)
    return len(df)


def incremental_symbol_futures(*, ccxt_client, http_client, root: Path,
                                symbol: str, fallback_days: int = 30) -> dict[str, int]:
    """Refresh funding/OI/L-S/liq for one symbol. These don't have resume — full re-fetch."""
    counts = {}
    since_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - fallback_days * 86400 * 1000

    f_df = fetch_funding_history(ccxt_client, symbol, since_ms)
    fpath = parquet_path(root, symbol, "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    if not f_df.empty:
        f_df.to_parquet(fpath, index=False)
    counts["funding"] = len(f_df)

    oi_df = fetch_oi_history(ccxt_client, symbol, since_ms)
    oipath = parquet_path(root, symbol, "oi", "futures")
    oipath.parent.mkdir(parents=True, exist_ok=True)
    if not oi_df.empty:
        oi_df.to_parquet(oipath, index=False)
    counts["oi"] = len(oi_df)

    ls_df = fetch_long_short_ratio(http_client, symbol, period="5m", limit=500)
    lspath = parquet_path(root, symbol, "ls_ratio", "futures")
    lspath.parent.mkdir(parents=True, exist_ok=True)
    if not ls_df.empty:
        ls_df.to_parquet(lspath, index=False)
    counts["ls_ratio"] = len(ls_df)

    liq_df = fetch_liquidations(http_client, symbol, since_ms)
    liqpath = parquet_path(root, symbol, "liq", "futures")
    liqpath.parent.mkdir(parents=True, exist_ok=True)
    if not liq_df.empty:
        liq_df.to_parquet(liqpath, index=False)
    counts["liq"] = len(liq_df)

    return counts


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/history"))
    parser.add_argument("--fallback-days", type=int, default=30)
    parser.add_argument("--skip-futures", action="store_true")
    parser.add_argument("--limit-symbols", type=int, default=None)
    parser.add_argument("--blacklist-path", type=Path,
                        default=Path("data/equity_blacklist.yaml"))
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    okx = ccxt.okx({"enableRateLimit": True})
    http = httpx.Client(timeout=30.0)

    symbols = list_active_perps(okx, blacklist_path=args.blacklist_path)
    if args.limit_symbols:
        symbols = symbols[:args.limit_symbols]
    log.info("incremental_start", n_symbols=len(symbols))

    total_new_bars = 0
    for i, sym in enumerate(symbols, start=1):
        try:
            for tf in TIMEFRAMES:
                n = incremental_symbol_timeframe(
                    client=okx, root=args.root,
                    symbol=sym, timeframe=tf,
                    fallback_days=args.fallback_days,
                )
                total_new_bars += n
                if n > 0:
                    log.info("ohlcv_incremental",
                             symbol=sym, timeframe=tf, rows=n,
                             progress=f"{i}/{len(symbols)}")
            if not args.skip_futures:
                counts = incremental_symbol_futures(
                    ccxt_client=okx, http_client=http, root=args.root,
                    symbol=sym, fallback_days=args.fallback_days,
                )
                log.info("futures_incremental", symbol=sym, **counts)
        except Exception as exc:  # pragma: no cover
            log.error("symbol_failed", symbol=sym, error=str(exc))
        time.sleep(0.15)

    log.info("incremental_complete", total_new_bars=total_new_bars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
