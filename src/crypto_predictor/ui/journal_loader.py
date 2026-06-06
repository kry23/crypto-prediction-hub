"""Loader for the Journal page: dated session journals + CHANGELOG as markdown.

Pure (no Streamlit) so it can be unit-tested. The page renders whatever this
returns into expanders.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class LogEntry:
    key: str    # stable id: an ISO date, or "changelog"
    label: str  # display title for the expander
    body: str   # raw markdown


def _first_h1(markdown: str) -> str | None:
    m = _H1.search(markdown)
    return m.group(1).strip() if m else None


def load_log_entries(root: Path) -> list[LogEntry]:
    """Return dated session journals (newest first), then CHANGELOG (last).

    Reads ``root/docs/sessions/*.md`` whose filenames start ``YYYY-MM-DD`` and
    appends ``root/CHANGELOG.md`` when present. Files without a date prefix are
    skipped. Never raises for absent files — returns whatever exists.
    """
    entries: list[LogEntry] = []

    sessions_dir = root / "docs" / "sessions"
    if sessions_dir.is_dir():
        dated: list[tuple[str, str, LogEntry]] = []  # (date, filename, entry)
        for path in sessions_dir.glob("*.md"):
            m = _DATE_PREFIX.match(path.name)
            if not m:
                continue
            date = m.group(1)
            body = path.read_text(encoding="utf-8")
            title = _first_h1(body) or path.stem
            dated.append(
                (date, path.name, LogEntry(key=date,
                                           label=f"{date} — {title}",
                                           body=body))
            )
        # Newest date first; ties broken by filename descending (deterministic).
        dated.sort(key=lambda t: (t[0], t[1]), reverse=True)
        entries = [entry for _, _, entry in dated]

    changelog = root / "CHANGELOG.md"
    if changelog.is_file():
        entries.append(
            LogEntry(key="changelog", label="📋 CHANGELOG",
                     body=changelog.read_text(encoding="utf-8"))
        )

    return entries
