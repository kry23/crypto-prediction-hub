"""CLI wrapper for run_backtest."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from crypto_predictor.backtest.runner import run_backtest
from crypto_predictor.logging_config import configure_logging


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-root", type=Path, default=Path("data/history"))
    parser.add_argument("--sentiment-cache", type=Path,
                        default=Path("data/sentiment_cache.db"))
    parser.add_argument("--global-cache", type=Path,
                        default=Path("data/global_cache.db"))
    parser.add_argument("--sector-map", type=Path, default=Path("data/sector_map.yaml"))
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--cal-days", type=int, default=30)
    parser.add_argument("--val-days", type=int, default=30)
    parser.add_argument("--slide-days", type=int, default=7)
    parser.add_argument("--sample-interval-hours", type=int, default=12)
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--report", type=Path,
                        default=Path("docs/backtest/report.md"))
    parser.add_argument("--calibration", type=Path,
                        default=Path("data/calibration_map.json"))
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        okx = ccxt.okx({"enableRateLimit": True})
        markets = okx.load_markets()
        symbols = [m["symbol"] for m in markets.values()
                   if m.get("swap") and m.get("settle") == "USDT" and m.get("active")]

    run_backtest(
        history_root=args.history_root,
        sentiment_cache=args.sentiment_cache,
        global_cache=args.global_cache,
        sector_map=args.sector_map,
        start=start, end=end,
        train_days=args.train_days, cal_days=args.cal_days, val_days=args.val_days,
        slide_days=args.slide_days,
        sample_interval_hours=args.sample_interval_hours,
        symbols=symbols,
        report_path=args.report,
        calibration_path=args.calibration,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
