"""Compute per-tilt correlation with 24h forward return on real ingested data."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.regime import detect_regime
from crypto_predictor.scoring.returns import actual_return
from crypto_predictor.scoring.tilt import (
    tilt_global, tilt_momentum, tilt_perp, tilt_sentiment,
    tilt_technical, tilt_volume,
)
from crypto_predictor.logging_config import configure_logging

TILT_FNS = {
    "tilt_momentum": tilt_momentum,
    "tilt_perp": tilt_perp,
    "tilt_volume": tilt_volume,
    "tilt_technical": tilt_technical,
    "tilt_sentiment": tilt_sentiment,
    "tilt_global": tilt_global,
}

log = structlog.get_logger(__name__)


def diagnose(history_root: Path, sentiment_cache: Path, global_cache: Path,
             sector_map: Path, symbols: list[str],
             start: datetime, end: datetime,
             sample_interval_hours: int = 24) -> pd.DataFrame:
    rows = []
    cursor = start
    sample_count = 0
    while cursor <= end:
        fetcher = FeatureFetcher(root=history_root, asof=cursor)
        regime = detect_regime(fetcher)
        for sym in symbols:
            try:
                feats = compute_features(
                    fetcher=fetcher, symbol=sym,
                    sentiment_cache=sentiment_cache, global_cache=global_cache,
                    sector_map_path=sector_map, mcap_rank=None,
                )
            except Exception:
                continue
            ret = actual_return(root=history_root, symbol=sym,
                                start_time=cursor, horizon_hours=24)
            if ret is None:
                continue
            row = {"asof": cursor, "symbol": sym, "regime": regime,
                   "actual_return": ret}
            for name, fn in TILT_FNS.items():
                row[name] = fn(feats)
            rows.append(row)
        sample_count += 1
        if sample_count % 5 == 0:
            log.info("diagnose_progress", samples=sample_count, rows=len(rows))
        cursor += timedelta(hours=sample_interval_hours)
    return pd.DataFrame(rows)


def report(df: pd.DataFrame) -> str:
    lines = ["# Tilt correlation diagnostic", ""]
    lines.append(f"**Sample size:** {len(df):,} prediction rows")
    lines.append("")

    lines.append("## Overall Pearson correlation with 24h return")
    lines.append("")
    lines.append("| Tilt | Pearson r | n |")
    lines.append("|---|---|---|")
    for tilt in TILT_FNS:
        sub = df[[tilt, "actual_return"]].dropna()
        if len(sub) < 10:
            r = float("nan")
        else:
            r = float(sub.corr(method="pearson").iloc[0, 1])
        lines.append(f"| {tilt} | {r:+.4f} | {len(sub):,} |")
    lines.append("")

    for regime in ("BULL", "BEAR", "CHOP"):
        sub_regime = df[df["regime"] == regime]
        if len(sub_regime) == 0:
            continue
        lines.append(f"## {regime} regime (n={len(sub_regime):,})")
        lines.append("")
        lines.append("| Tilt | Pearson r |")
        lines.append("|---|---|")
        for tilt in TILT_FNS:
            sub = sub_regime[[tilt, "actual_return"]].dropna()
            r = float(sub.corr(method="pearson").iloc[0, 1]) if len(sub) >= 10 else float("nan")
            lines.append(f"| {tilt} | {r:+.4f} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-root", type=Path, default=Path("data/history"))
    parser.add_argument("--sentiment-cache", type=Path, default=Path("data/sentiment_cache.db"))
    parser.add_argument("--global-cache", type=Path, default=Path("data/global_cache.db"))
    parser.add_argument("--sector-map", type=Path, default=Path("data/sector_map.yaml"))
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--symbols", type=str, required=True)
    parser.add_argument("--sample-interval-hours", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    df = diagnose(args.history_root, args.sentiment_cache, args.global_cache,
                  args.sector_map, symbols, start, end, args.sample_interval_hours)
    if df.empty:
        log.error("no_data")
        return 1
    md = report(df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    log.info("diagnostic_complete", output=str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
