"""Fetch BTC dominance, ETH/BTC, total mcap, sector indices via CoinGecko."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.features.families.global_ctx import write_global_cache

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"


def fetch_btc_dom_trend(*, http_client) -> float:
    """Return current BTC dominance percentage (simple snapshot — trend computation TBD)."""
    try:
        resp = http_client.get(COINGECKO_GLOBAL, timeout=20.0)
        if resp.status_code != 200:
            return 0.0
        data = resp.json().get("data", {})
        return float(data.get("market_cap_percentage", {}).get("btc", 0.0)) / 100.0
    except Exception:
        return 0.0


def write_global_for_asof(*, db: Path, timestamp: str,
                          btc_dom_trend_7d: float, eth_btc_trend_7d: float,
                          total_mcap_z: float,
                          sector_btc: float, sector_eth: float,
                          sector_defi: float, sector_l1: float) -> None:
    """Pass-through to Plan A's `write_global_cache`."""
    write_global_cache(
        db=db, timestamp=timestamp,
        btc_dom_trend_7d=btc_dom_trend_7d,
        eth_btc_trend_7d=eth_btc_trend_7d,
        total_mcap_z=total_mcap_z,
        sector_btc=sector_btc, sector_eth=sector_eth,
        sector_defi=sector_defi, sector_l1=sector_l1,
    )
