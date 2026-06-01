"""features.db — feature snapshot cache for replay and audit."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_snapshot (
    symbol       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    value        REAL,
    PRIMARY KEY (symbol, timestamp, feature_name)
);
CREATE INDEX IF NOT EXISTS idx_fs_symbol_ts ON feature_snapshot(symbol, timestamp);
"""


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def write_snapshot(path: Path, symbol: str, timestamp: str,
                   features: dict[str, float]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO feature_snapshot(symbol,timestamp,feature_name,value) "
            "VALUES (?,?,?,?)",
            [(symbol, timestamp, name, value) for name, value in features.items()],
        )
        conn.commit()
    finally:
        conn.close()


def read_snapshot(path: Path, symbol: str, timestamp: str) -> dict[str, float]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT feature_name, value FROM feature_snapshot "
            "WHERE symbol=? AND timestamp=?",
            (symbol, timestamp),
        ).fetchall()
        return {name: value for name, value in rows}
    finally:
        conn.close()
