"""Sanity-check the ingested parquet store: counts, coverage, freshness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/history"))
    args = parser.parse_args()

    ohlcv_root = args.root / "ohlcv"
    futures_root = args.root / "futures"
    if not ohlcv_root.exists():
        print(f"ERROR: {ohlcv_root} does not exist. Run ingest_history first.")
        return 1

    symbols = sorted(p.name for p in ohlcv_root.iterdir() if p.is_dir())
    print(f"Symbols ingested: {len(symbols)}")

    timeframes = ["15m", "1h", "4h", "1d"]
    rows_per_tf: dict[str, int] = {tf: 0 for tf in timeframes}
    missing_tf: list[tuple[str, str]] = []
    stale_count = 0
    stale_cutoff = (datetime.now(timezone.utc).timestamp() - 86400) * 1000

    for sym in symbols:
        for tf in timeframes:
            p = ohlcv_root / sym / f"{tf}.parquet"
            if not p.exists():
                missing_tf.append((sym, tf))
                continue
            df = pd.read_parquet(p)
            rows_per_tf[tf] += len(df)
            if not df.empty and df["timestamp"].max() < stale_cutoff:
                stale_count += 1

    print(f"\nOHLCV rows by timeframe:")
    for tf, n in rows_per_tf.items():
        print(f"  {tf}: {n:,}")
    print(f"\nMissing (symbol, timeframe) pairs: {len(missing_tf)}")
    if missing_tf[:5]:
        print(f"  examples: {missing_tf[:5]}")
    print(f"\nSymbol/timeframe pairs with stale last bar (>24h old): {stale_count}")

    # Futures coverage
    if futures_root.exists():
        futures_symbols = sorted(p.name for p in futures_root.iterdir() if p.is_dir())
        print(f"\nFutures-data symbols: {len(futures_symbols)}")
    else:
        print(f"\nFutures-data symbols: 0 (no futures dir yet)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
