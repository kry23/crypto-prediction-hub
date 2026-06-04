"""Bootstrap (or migrate) the PostgreSQL schema for crypto-predictor v1.0.

Reads all ``.sql`` files under ``migrations/`` in lexical order. For each one:

  1. SHA-256 the file content.
  2. Check the ``_migrations`` table for that version.
  3. If absent (or the recorded sha256 differs) apply the file inside a
     transaction and INSERT the version + sha256 into ``_migrations``.

Run during cutover (after ``createdb``, before
``migrate_sqlite_to_postgres.py``)::

    python scripts/init_postgres_schema.py \\
        --pg postgresql://crypto_predictor:PASSWORD@127.0.0.1:5432/crypto_predictor

Dry-run mode (no PG required) — just lists the migrations the script *would*
apply::

    python scripts/init_postgres_schema.py --pg "" --dry-run

The script is idempotent: re-running on a fully migrated database is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import structlog

# Project root onto sys.path so this script works when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging  # noqa: E402

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers (all PG-free so dry-run works without psycopg installed)
# ---------------------------------------------------------------------------

def list_migrations(migrations_dir: Path) -> list[tuple[str, str, Path]]:
    """Return ``(version, sha256, path)`` for each ``*.sql`` file in
    ``migrations_dir``, sorted lexically.

    The version is the file stem (``001_initial_schema.sql`` → ``001_initial_schema``).
    Non-``.sql`` files (READMEs, notes) are ignored.
    """
    if not migrations_dir.is_dir():
        raise FileNotFoundError(
            f"migrations directory not found: {migrations_dir}"
        )
    out: list[tuple[str, str, Path]] = []
    for path in sorted(migrations_dir.iterdir(), key=lambda p: p.name):
        if path.suffix.lower() != ".sql":
            continue
        if not path.is_file():
            continue
        version = path.stem
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        out.append((version, sha, path))
    return out


# ---------------------------------------------------------------------------
# PG-dependent helpers (lazy import so dry-run works without psycopg)
# ---------------------------------------------------------------------------

def _open_pg(url: str):
    """Lazy import psycopg so dry-run mode doesn't require it installed."""
    import psycopg  # noqa: PLC0415 — intentional lazy import

    return psycopg.connect(url)


def _ensure_migrations_table(conn) -> None:
    """Create the ``_migrations`` tracker if missing (chicken-and-egg case
    where the bootstrap runs against a brand-new DB)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                version     VARCHAR(40) PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sha256      VARCHAR(64) NOT NULL
            )
            """
        )
    conn.commit()


def applied_versions(conn) -> dict[str, str]:
    """Read ``_migrations``; create it if missing. Return ``{version: sha256}``
    for everything already applied."""
    _ensure_migrations_table(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT version, sha256 FROM _migrations")
        return {row[0]: row[1] for row in cur.fetchall()}


def apply_migration(conn, version: str, sha256_hex: str,
                    sql_path: Path) -> None:
    """Apply a single migration file in a single transaction; record in
    ``_migrations``. Raises on SQL error (transaction rolled back)."""
    sql_text = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        try:
            cur.execute(sql_text)
            cur.execute(
                "INSERT INTO _migrations (version, sha256) VALUES (%s, %s) "
                "ON CONFLICT (version) DO UPDATE "
                "SET sha256 = EXCLUDED.sha256, applied_at = NOW()",
                (version, sha256_hex),
            )
        except Exception:
            conn.rollback()
            raise
    conn.commit()


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

def run_init(*, pg_url: str, migrations_dir: Path,
             dry_run: bool = False) -> dict[str, list[str]]:
    """Apply pending migrations. Returns ``{"applied": [...], "skipped": [...]}``.

    Dry-run mode skips the PG connection entirely and reports every discovered
    migration under ``"applied"`` (i.e. what *would* be applied on a fresh
    database).
    """
    migrations = list_migrations(migrations_dir)
    summary: dict[str, list[str]] = {"applied": [], "skipped": []}

    if dry_run:
        for version, _sha, _path in migrations:
            summary["applied"].append(version)
        log.info("init_dry_run", count=len(summary["applied"]),
                 versions=summary["applied"])
        return summary

    if not pg_url:
        raise ValueError("pg_url is required when --dry-run is not set")

    conn = _open_pg(pg_url)
    try:
        already = applied_versions(conn)
        for version, sha, path in migrations:
            prior_sha = already.get(version)
            if prior_sha == sha:
                summary["skipped"].append(version)
                log.info("init_skip", version=version, reason="already_applied")
                continue
            if prior_sha is not None and prior_sha != sha:
                log.warning("init_sha_drift", version=version,
                            prior_sha=prior_sha, new_sha=sha)
            apply_migration(conn, version, sha, path)
            summary["applied"].append(version)
            log.info("init_apply", version=version, sha=sha)
    finally:
        conn.close()

    return summary


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Bootstrap the PostgreSQL schema for crypto-predictor v1.0.",
    )
    parser.add_argument(
        "--pg", type=str, required=True,
        help="DATABASE_URL for the target PG (empty string allowed with --dry-run)",
    )
    parser.add_argument(
        "--migrations", type=Path,
        default=Path(__file__).resolve().parent.parent / "migrations",
        help="Directory containing *.sql migration files (default: ./migrations)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List the migrations that would be applied; do not connect to PG.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_init(
            pg_url=args.pg,
            migrations_dir=args.migrations,
            dry_run=args.dry_run,
        )
    except Exception as e:  # pragma: no cover — exercised in cutover smoke
        log.error("init_failed", error=str(e))
        return 1

    log.info("init_complete", **summary)
    print("\nMigration summary:")
    print(f"  applied: {summary['applied'] or '[]'}")
    print(f"  skipped: {summary['skipped'] or '[]'}")
    return 0


# Backwards-compat alias for callers that imported the older internal name.
_apply_migration = apply_migration


def __getattr__(name: str) -> Any:  # pragma: no cover
    raise AttributeError(name)


if __name__ == "__main__":
    sys.exit(main())
