"""Generate data/mcap_ranks.yaml from CoinGecko top-N markets.

Output format: flat YAML map of `BASE_CCY: rank` (1-based). Consumed by
_job_predict_scan to pick the top-30 mcap coins for NewsAPI sentiment.

Without this file the sentiment block in jobs.py silently no-ops because
every symbol's rank is None, so `top_symbols` is empty.

Usage: `python scripts/generate_mcap_ranks.py [--top 250]`
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import structlog
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging

log = structlog.get_logger(__name__)

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"


def fetch_top_markets(top: int = 250) -> list[dict]:
    """CoinGecko returns at most 250 per page on the free tier."""
    per_page = min(top, 250)
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": 1,
        "sparkline": "false",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(COINGECKO_MARKETS, params=params)
        resp.raise_for_status()
        return resp.json()


def build_mcap_map(markets: list[dict]) -> dict[str, int]:
    """Build {BASE_CCY_UPPERCASE: rank}. CoinGecko's `symbol` field is the
    base currency in lowercase; we uppercase to match ccxt_to_base_ccy output."""
    out: dict[str, int] = {}
    for entry in markets:
        symbol = (entry.get("symbol") or "").upper()
        rank = entry.get("market_cap_rank")
        if not symbol or rank is None:
            continue
        # On duplicate base symbols (e.g., chains share tickers), keep the
        # higher-mcap one — the list comes pre-sorted, so first wins.
        if symbol not in out:
            out[symbol] = int(rank)
    return out


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=250,
                        help="How many markets to fetch (max 250 on free tier).")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent.parent
                                / "data" / "mcap_ranks.yaml")
    args = parser.parse_args()

    log.info("fetching_top_markets", top=args.top)
    markets = fetch_top_markets(args.top)
    mcap_map = build_mcap_map(markets)
    log.info("built_mcap_map", n=len(mcap_map))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(mcap_map, sort_keys=False),
                         encoding="utf-8")
    log.info("mcap_ranks_written", path=str(args.out), n=len(mcap_map))
    return 0


if __name__ == "__main__":
    sys.exit(main())
