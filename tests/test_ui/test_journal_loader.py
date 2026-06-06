"""Tests for the Journal page's markdown loader (pure, no Streamlit)."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.ui.journal_loader import LogEntry, load_log_entries


def _make_root(tmp_path: Path, sessions: dict[str, str],
               changelog: str | None = None) -> Path:
    sdir = tmp_path / "docs" / "sessions"
    sdir.mkdir(parents=True)
    for name, content in sessions.items():
        (sdir / name).write_text(content, encoding="utf-8")
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_entries_sorted_newest_first(tmp_path):
    root = _make_root(tmp_path, {
        "2026-06-03-a.md": "# Old\nbody",
        "2026-06-07-b.md": "# New\nbody",
        "2026-06-05-c.md": "# Mid\nbody",
    })
    keys = [e.key for e in load_log_entries(root)]
    assert keys == ["2026-06-07", "2026-06-05", "2026-06-03"]


def test_label_uses_first_h1(tmp_path):
    root = _make_root(tmp_path, {"2026-06-07-x.md": "# Post-cutover fix\n\ntext"})
    assert load_log_entries(root)[0].label == "2026-06-07 — Post-cutover fix"


def test_label_falls_back_to_stem_when_no_h1(tmp_path):
    root = _make_root(tmp_path, {"2026-06-07-no-title.md": "no heading here"})
    assert load_log_entries(root)[0].label == "2026-06-07 — 2026-06-07-no-title"


def test_non_dated_files_skipped(tmp_path):
    root = _make_root(tmp_path, {"README.md": "# nope", "2026-06-07-ok.md": "# ok"})
    assert [e.key for e in load_log_entries(root)] == ["2026-06-07"]


def test_same_date_broken_by_filename_descending(tmp_path):
    root = _make_root(tmp_path, {
        "2026-06-07-aaa.md": "# A",
        "2026-06-07-zzz.md": "# Z",
    })
    labels = [e.label for e in load_log_entries(root)]
    assert labels == ["2026-06-07 — Z", "2026-06-07 — A"]


def test_changelog_appended_last(tmp_path):
    root = _make_root(tmp_path, {"2026-06-07-x.md": "# x"},
                      changelog="# Changelog\nstuff")
    entries = load_log_entries(root)
    assert entries[-1].key == "changelog"
    assert entries[-1].label == "📋 CHANGELOG"
    assert "stuff" in entries[-1].body


def test_changelog_omitted_when_absent(tmp_path):
    root = _make_root(tmp_path, {"2026-06-07-x.md": "# x"})
    assert all(e.key != "changelog" for e in load_log_entries(root))


def test_missing_sessions_dir_does_not_raise(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# c", encoding="utf-8")
    assert [e.key for e in load_log_entries(tmp_path)] == ["changelog"]


def test_empty_root_returns_empty_list(tmp_path):
    assert load_log_entries(tmp_path) == []


def test_body_is_raw_markdown(tmp_path):
    content = "# Title\n\n- bullet\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    root = _make_root(tmp_path, {"2026-06-07-x.md": content})
    assert load_log_entries(root)[0].body == content


def test_returns_logentry_instances(tmp_path):
    root = _make_root(tmp_path, {"2026-06-07-x.md": "# x\nbody"})
    entries = load_log_entries(root)
    assert all(isinstance(e, LogEntry) for e in entries)
