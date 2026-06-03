"""Fetch BTC dominance, ETH/BTC, total mcap, sector indices via CoinGecko."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

from crypto_predictor.features.families.global_ctx import write_global_cache

log = structlog.get_logger(__name__)

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"

_ALLOWED_SECTOR_COLS = {"sector_btc", "sector_eth", "sector_defi", "sector_l1"}


def fetch_btc_dom_trend(*, http_client) -> float:
    """Return current BTC dominance fraction (snapshot)."""
    try:
        resp = http_client.get(COINGECKO_GLOBAL, timeout=20.0)
        if resp.status_code != 200:
            return 0.0
        data = resp.json().get("data", {})
        return float(data.get("market_cap_percentage", {}).get("btc", 0.0)) / 100.0
    except Exception:
        return 0.0


def fetch_dominance_snapshot(*, http_client) -> dict[str, float]:
    """Return {'btc': fraction, 'eth': fraction} from CoinGecko /global."""
    try:
        resp = http_client.get(COINGECKO_GLOBAL, timeout=20.0)
        if resp.status_code != 200:
            return {"btc": 0.0, "eth": 0.0}
        mcp = resp.json().get("data", {}).get("market_cap_percentage", {})
        return {
            "btc": float(mcp.get("btc", 0.0)) / 100.0,
            "eth": float(mcp.get("eth", 0.0)) / 100.0,
        }
    except Exception:
        return {"btc": 0.0, "eth": 0.0}


def read_sector_history(db: Path, sector_col: str,
                        lookback_days: int = 7) -> list[tuple[str, float]]:
    """Return [(timestamp, value), ...] ASC for last `lookback_days` of snapshots."""
    if sector_col not in _ALLOWED_SECTOR_COLS:
        raise ValueError(f"invalid sector_col: {sector_col}")
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            f"SELECT timestamp, {sector_col} FROM global_cache "
            f"WHERE timestamp >= datetime('now', ?) "
            f"ORDER BY timestamp ASC",
            (f"-{int(lookback_days)} days",),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [(ts, float(v)) for ts, v in rows if v is not None]


def compute_trend_pct(history: list[tuple[str, float]]) -> float:
    """Relative change from first to last sample; 0.0 if warming up or zero denom."""
    if len(history) < 2:
        return 0.0
    first = history[0][1]
    last = history[-1][1]
    if first == 0:
        return 0.0
    return (last - first) / first


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
