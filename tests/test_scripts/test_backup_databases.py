# tests/test_scripts/test_backup_databases.py
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.backup_databases import (
    backup_all,
    prune_old,
    snapshot_one,
    timestamp_suffix,
)


def _make_sqlite_with_row(path: Path, row: tuple[int, str]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO t VALUES (?, ?)", row)
    conn.commit()
    conn.close()


def test_timestamp_suffix_is_utc_yyyymmddhhmm():
    fixed = datetime(2026, 6, 3, 6, 45, tzinfo=timezone.utc)
    assert timestamp_suffix(fixed) == "2026-06-03-0645"


def test_snapshot_one_creates_readable_copy(tmp_path: Path):
    src = tmp_path / "src.db"
    _make_sqlite_with_row(src, (42, "alpha"))
    dst = tmp_path / "backup" / "src-2026-06-03.db"

    size = snapshot_one(src, dst)
    assert size > 0
    assert dst.exists()

    conn = sqlite3.connect(str(dst))
    rows = conn.execute("SELECT id, name FROM t").fetchall()
    conn.close()
    assert rows == [(42, "alpha")]


def test_snapshot_one_works_while_source_open_for_write(tmp_path: Path):
    """Online backup must succeed even with a live writer connection."""
    src = tmp_path / "src.db"
    _make_sqlite_with_row(src, (1, "x"))
    writer = sqlite3.connect(str(src))
    try:
        writer.execute("INSERT INTO t VALUES (2, 'y')")
        # Note: don't commit — backup should still get the committed state
        dst = tmp_path / "backup" / "src.db"
        snapshot_one(src, dst)
        assert dst.exists()
        conn = sqlite3.connect(str(dst))
        rows = conn.execute("SELECT id FROM t ORDER BY id").fetchall()
        conn.close()
        assert (1,) in rows  # committed row present
    finally:
        writer.close()


def test_prune_old_keeps_n_most_recent(tmp_path: Path):
    for name in [
        "predictions-2026-06-01-0700.db",
        "predictions-2026-06-02-0700.db",
        "predictions-2026-06-03-0700.db",
        "predictions-2026-06-04-0700.db",
        "global_cache-2026-06-04-0700.db",
    ]:
        (tmp_path / name).write_bytes(b"x")

    deleted = prune_old(tmp_path, "predictions", keep=2)
    assert len(deleted) == 2
    remaining = sorted(p.name for p in tmp_path.glob("predictions-*.db"))
    assert remaining == [
        "predictions-2026-06-03-0700.db",
        "predictions-2026-06-04-0700.db",
    ]
    assert (tmp_path / "global_cache-2026-06-04-0700.db").exists()


def test_prune_old_no_op_when_under_threshold(tmp_path: Path):
    (tmp_path / "predictions-2026-06-01-0700.db").write_bytes(b"x")
    deleted = prune_old(tmp_path, "predictions", keep=14)
    assert deleted == []


def test_backup_all_skips_missing_dbs(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    _make_sqlite_with_row(source / "predictions.db", (1, "a"))
    # global_cache.db and sentiment_cache.db absent

    backup_dir = tmp_path / "backups"
    fixed = datetime(2026, 6, 3, 7, 0, tzinfo=timezone.utc)
    results = backup_all(source_root=source, backup_dir=backup_dir, keep=14,
                          now=fixed)

    assert results["predictions"] is not None
    assert results["predictions"] > 0
    assert results["global_cache"] is None
    assert results["sentiment_cache"] is None
    assert (backup_dir / "predictions-2026-06-03-0700.db").exists()


def test_backup_all_writes_all_three_when_present(tmp_path: Path):
    source = tmp_path / "src"
    (source / "data").mkdir(parents=True)
    _make_sqlite_with_row(source / "predictions.db", (1, "p"))
    _make_sqlite_with_row(source / "data" / "global_cache.db", (1, "g"))
    _make_sqlite_with_row(source / "data" / "sentiment_cache.db", (1, "s"))

    backup_dir = tmp_path / "backups"
    fixed = datetime(2026, 6, 3, 7, 0, tzinfo=timezone.utc)
    results = backup_all(source_root=source, backup_dir=backup_dir, keep=14,
                          now=fixed)

    assert all(v is not None and v > 0 for v in results.values())
    assert (backup_dir / "predictions-2026-06-03-0700.db").exists()
    assert (backup_dir / "global_cache-2026-06-03-0700.db").exists()
    assert (backup_dir / "sentiment_cache-2026-06-03-0700.db").exists()


def test_backup_all_prunes_old_within_each_db_family(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    _make_sqlite_with_row(source / "predictions.db", (1, "p"))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for stamp in ["2026-05-01-0700", "2026-05-02-0700", "2026-05-03-0700"]:
        (backup_dir / f"predictions-{stamp}.db").write_bytes(b"old")

    fixed = datetime(2026, 6, 3, 7, 0, tzinfo=timezone.utc)
    backup_all(source_root=source, backup_dir=backup_dir, keep=2, now=fixed)

    remaining = sorted(p.name for p in backup_dir.glob("predictions-*.db"))
    assert remaining == [
        "predictions-2026-05-03-0700.db",
        "predictions-2026-06-03-0700.db",
    ]
