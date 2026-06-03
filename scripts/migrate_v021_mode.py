"""Add mode + feature_completeness + missing_features columns and backfill."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import structlog

from crypto_predictor.logging_config import configure_logging

log = structlog.get_logger(__name__)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def migrate_to_v021(db_path: Path) -> None:
    """Idempotent: adds columns if missing, runs backfill once per column."""
    conn = sqlite3.connect(str(db_path))
    try:
        if not _column_exists(conn, "predictions", "mode"):
            conn.execute(
                "ALTER TABLE predictions ADD COLUMN mode TEXT NOT NULL "
                "DEFAULT 'live'"
            )
            log.info("migration_added_column", column="mode")
        if not _column_exists(conn, "predictions", "feature_completeness"):
            conn.execute(
                "ALTER TABLE predictions ADD COLUMN feature_completeness TEXT "
                "NOT NULL DEFAULT 'full'"
            )
            log.info("migration_added_column", column="feature_completeness")
        if not _column_exists(conn, "predictions", "missing_features"):
            conn.execute(
                "ALTER TABLE predictions ADD COLUMN missing_features TEXT NULL"
            )
            log.info("migration_added_column", column="missing_features")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_mode "
            "ON predictions(mode)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_completeness "
            "ON predictions(feature_completeness)"
        )
        # Backfill the 2026-06-02 11:30 UTC cohort (NewsAPI + global stub period)
        cur = conn.execute(
            "UPDATE predictions "
            "SET feature_completeness='degraded', "
            "    missing_features='sentiment,global' "
            "WHERE id NOT LIKE 'dryrun_%' "
            "  AND created_at LIKE '2026-06-02%' "
            "  AND feature_completeness='full'"
        )
        log.info("migration_backfill_done", rows_updated=cur.rowcount)
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    args = parser.parse_args()
    if not args.db.exists():
        log.error("db_missing", path=str(args.db))
        return 1
    migrate_to_v021(args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
