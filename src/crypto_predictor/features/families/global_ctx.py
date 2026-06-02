"""Family 6 — cross-coin / global context. Reads from global_cache.db."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from crypto_predictor.features.fetcher import FeatureFetcher

NEUTRAL = {
    "btc_dom_trend_7d": 0.0,
    "eth_btc_trend_7d": 0.0,
    "total_mcap_z": 0.0,
    "sector_strength_24h": 0.0,
    "coin_btc_corr_30d": 0.0,
}

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS global_cache (
    timestamp         TEXT PRIMARY KEY,
    btc_dom_trend_7d  REAL,
    eth_btc_trend_7d  REAL,
    total_mcap_z      REAL,
    sector_btc        REAL,
    sector_eth        REAL,
    sector_defi       REAL,
    sector_l1         REAL
);

CREATE TABLE IF NOT EXISTS coin_btc_corr (
    symbol     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    corr_30d   REAL,
    PRIMARY KEY (symbol, timestamp)
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)
    conn.commit()


def write_global_cache(db: Path, timestamp: str,
                       *, btc_dom_trend_7d: float, eth_btc_trend_7d: float,
                       total_mcap_z: float, sector_btc: float,
                       sector_eth: float, sector_defi: float,
                       sector_l1: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO global_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, btc_dom_trend_7d, eth_btc_trend_7d, total_mcap_z,
             sector_btc, sector_eth, sector_defi, sector_l1),
        )
        conn.commit()
    finally:
        conn.close()


def write_coin_corr(db: Path, symbol: str, timestamp: str,
                    corr_30d: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO coin_btc_corr VALUES (?, ?, ?)",
            (symbol, timestamp, corr_30d),
        )
        conn.commit()
    finally:
        conn.close()


def compute_global_features(fetcher: FeatureFetcher, symbol: str,
                            *, cache_db: Path, sector: str = "l1") -> dict[str, float]:
    if not cache_db.exists():
        return dict(NEUTRAL)
    conn = sqlite3.connect(str(cache_db))
    try:
        _ensure_schema(conn)
        g = conn.execute(
            "SELECT btc_dom_trend_7d, eth_btc_trend_7d, total_mcap_z, "
            "       sector_btc, sector_eth, sector_defi, sector_l1 "
            "FROM global_cache WHERE timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (fetcher.asof.isoformat(),),
        ).fetchone()
        if g is None:
            global_out = dict(NEUTRAL)
        else:
            sector_map = {"btc": g[3], "eth": g[4], "defi": g[5], "l1": g[6]}
            global_out = {
                "btc_dom_trend_7d": g[0] or 0.0,
                "eth_btc_trend_7d": g[1] or 0.0,
                "total_mcap_z": g[2] or 0.0,
                "sector_strength_24h": sector_map.get(sector, 0.0) or 0.0,
            }
        c = conn.execute(
            "SELECT corr_30d FROM coin_btc_corr "
            "WHERE symbol = ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, fetcher.asof.isoformat()),
        ).fetchone()
        global_out["coin_btc_corr_30d"] = (c[0] if c else 0.0) or 0.0
        return global_out
    finally:
        conn.close()
