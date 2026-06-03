"""Snapshot SQLite databases to a versioned backup directory.

Why: predictions.db is the single source of truth for the validation loop +
rolling metrics + pattern history. A corruption or schema mistake could erase
months of live track record. Snapshots use SQLite's online backup API so they
are safe to run while the scheduler is writing.

Schedule daily at 06:45 UTC (after validate_pending at 06:30 UTC closes the
day's predictions, so the snapshot includes the freshly-realized outcomes).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from crypto_predictor.logging_config import configure_logging

log = structlog.get_logger(__name__)

DEFAULT_BACKUP_DIR = Path.home() / ".crypto-predictor-backups"
DEFAULT_KEEP = 14
DB_SOURCES = [
    ("predictions", Path("predictions.db")),
    ("global_cache", Path("data") / "global_cache.db"),
    ("sentiment_cache", Path("data") / "sentiment_cache.db"),
]


def timestamp_suffix(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d-%H%M")


def snapshot_one(src: Path, dst: Path) -> int:
    """Use sqlite3 online backup to copy src → dst. Returns dst size in bytes."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return dst.stat().st_size


def prune_old(backup_dir: Path, prefix: str, keep: int) -> list[Path]:
    """Keep most recent `keep` snapshots matching `{prefix}-*.db`. Returns deleted."""
    candidates = sorted(
        backup_dir.glob(f"{prefix}-*.db"),
        key=lambda p: p.name,
        reverse=True,
    )
    to_delete = candidates[keep:]
    for p in to_delete:
        p.unlink()
    return to_delete


def backup_all(*, source_root: Path, backup_dir: Path, keep: int,
               now: datetime | None = None) -> dict[str, int | None]:
    """Snapshot every present DB. Returns {name: bytes or None if missing}."""
    suffix = timestamp_suffix(now)
    results: dict[str, int | None] = {}
    for name, relpath in DB_SOURCES:
        src = source_root / relpath
        if not src.exists():
            log.info("backup_skip_missing", db=name, path=str(src))
            results[name] = None
            continue
        dst = backup_dir / f"{name}-{suffix}.db"
        size = snapshot_one(src, dst)
        deleted = prune_old(backup_dir, name, keep)
        log.info("backup_ok", db=name, dst=str(dst), bytes=size,
                 pruned=len(deleted))
        results[name] = size
    return results


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path.cwd(),
                        help="Project root containing predictions.db etc.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                        help="How many recent snapshots to retain per DB.")
    args = parser.parse_args()

    log.info("backup_start", source_root=str(args.source_root),
             backup_dir=str(args.backup_dir), keep=args.keep)
    results = backup_all(source_root=args.source_root,
                          backup_dir=args.backup_dir, keep=args.keep)
    total_bytes = sum(v for v in results.values() if v is not None)
    log.info("backup_complete", total_bytes=total_bytes,
             dbs_backed_up=sum(1 for v in results.values() if v is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
