"""Continuous SQLite -> PostgreSQL sync bridge (v1.0 interim).

The prediction pipeline (scan / validate / recalibrate) writes SQLite; the
Streamlit UI reads PostgreSQL. Until the pipeline is converted to PG natively
(planned v1.1), this bridge mirrors SQLite into PG on a timer (systemd) so the
UI shows fresh data -- including validation status UPDATES, not just new
inserts.

Difference vs ``migrate_sqlite_to_postgres.py`` (the one-time cutover port):
that script is INSERT-only (``ON CONFLICT DO NOTHING``), so a row whose
``status`` flipped from ``pending`` to ``correct`` in SQLite would never update
in PG. This bridge UPSERTs mutable tables (``ON CONFLICT DO UPDATE``) so
validation outcomes propagate. The large append-only ``predictions_features``
table stays insert-only to avoid rewriting immutable rows every tick.

Usage (systemd timer ExecStart):
    python scripts/sync_sqlite_to_pg.py \\
        --predictions ./predictions.db \\
        --sentiment ./data/sentiment_cache.db \\
        --global ./data/global_cache.db \\
        --pg "$DATABASE_URL"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import structlog

# Project root onto sys.path so this script works when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging  # noqa: E402
from scripts.migrate_sqlite_to_postgres import (  # noqa: E402
    _TABLE_PKS,
    _open_pg,
    _quote_col,
    _read_table,
)

log = structlog.get_logger(__name__)

# Append-only tables: rows are immutable once written, so insert-only
# (DO NOTHING) is correct and avoids re-writing large immutable tables.
INSERT_ONLY: frozenset[str] = frozenset({"predictions_features"})

# (table, which-source-db) in FK-safe order (predictions before *_features).
_SYNC_ORDER: tuple[tuple[str, str], ...] = (
    ("predictions", "predictions_db"),
    ("predictions_features", "predictions_db"),
    ("calibration_maps", "predictions_db"),
    ("regime_log", "predictions_db"),
    ("metrics_rolling", "predictions_db"),
    ("patterns", "predictions_db"),
    ("runs", "predictions_db"),
    ("sentiment_cache", "sentiment_db"),
    ("global_cache", "global_db"),
    ("coin_btc_corr", "global_db"),
)


def build_upsert_sql(table: str, columns: list[str]) -> str:
    """Return an INSERT ... ON CONFLICT statement for `table`.

    Mutable tables get ``DO UPDATE SET <non-pk cols> = EXCLUDED.<col>`` so
    changed rows (e.g. a validated prediction's ``status``) propagate. Tables
    in ``INSERT_ONLY`` -- or whose columns are all part of the PK -- get
    ``DO NOTHING`` (nothing non-key to update).
    """
    pk = _TABLE_PKS[table]
    col_list = ", ".join(_quote_col(c) for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    pk_list = ", ".join(_quote_col(c) for c in pk)
    non_pk = [c for c in columns if c not in pk]
    if table in INSERT_ONLY or not non_pk:
        conflict = f"ON CONFLICT ({pk_list}) DO NOTHING"
    else:
        sets = ", ".join(
            f"{_quote_col(c)} = EXCLUDED.{_quote_col(c)}" for c in non_pk
        )
        conflict = f"ON CONFLICT ({pk_list}) DO UPDATE SET {sets}"
    return (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) {conflict}"
    )


def _sync_table(pg_conn: Any, src_db: Path, table: str) -> int:
    """Read `table` from SQLite and UPSERT into PG. Returns rows processed."""
    cols, rows = _read_table(src_db, table)
    if not cols or not rows:
        return 0
    sql = build_upsert_sql(table, cols)
    with pg_conn.cursor() as cur:
        cur.executemany(sql, rows)
    pg_conn.commit()
    return len(rows)


def run_sync(*, predictions_db: Path, sentiment_db: Path, global_db: Path,
             pg_conn: Any) -> dict[str, int]:
    """Sync every mirrored table. Returns {table: rows_processed}."""
    paths = {
        "predictions_db": predictions_db,
        "sentiment_db": sentiment_db,
        "global_db": global_db,
    }
    summary: dict[str, int] = {}
    for table, which in _SYNC_ORDER:
        summary[table] = _sync_table(pg_conn, paths[which], table)
    return summary


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Mirror the SQLite pipeline DBs into PostgreSQL for the UI.",
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--sentiment", type=Path, required=True)
    parser.add_argument("--global", type=Path, required=True, dest="global_db")
    parser.add_argument("--pg", type=str, required=True,
                        help="DATABASE_URL for the target PG")
    args = parser.parse_args(argv)

    conn = _open_pg(args.pg)
    try:
        summary = run_sync(
            predictions_db=args.predictions,
            sentiment_db=args.sentiment,
            global_db=args.global_db,
            pg_conn=conn,
        )
    finally:
        conn.close()
    log.info("sync_complete", total=sum(summary.values()), **summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
