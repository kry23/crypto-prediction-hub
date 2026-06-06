# Journal page — design

**Date:** 2026-06-07
**Status:** approved (brainstorm)

## Purpose

Surface the project's dated session journals + CHANGELOG inside the Streamlit UI
(`krypredictor.com`) as a newest-first "daily log" so the operator can read what
happened/changed without opening the repo.

## Architecture

Two new modules, following the existing UI pattern (thin page + testable helper):

### `src/crypto_predictor/ui/journal_loader.py` (pure, testable)

```python
@dataclass(frozen=True)
class LogEntry:
    key: str        # stable id, e.g. "2026-06-07" or "changelog"
    label: str      # display title, e.g. "2026-06-07 — post-cutover model fix"
    body: str       # raw markdown

def load_log_entries(root: Path) -> list[LogEntry]:
    ...
```

Behaviour:
- Discover `root/docs/sessions/*.md`. Parse the leading `YYYY-MM-DD` from each
  filename as the entry date. Files without a parseable date prefix are skipped.
- `label` = `"<date> — <title>"` where `<title>` is the first `# H1` line's text
  (stripped of leading `#`), or the filename stem if no H1.
- Sort journal entries **newest date first**. Ties (same date) broken by
  filename descending — stable + deterministic.
- Append `root/CHANGELOG.md` as a final entry (`key="changelog"`,
  `label="📋 CHANGELOG"`) when the file exists.
- Missing `docs/sessions/` dir or missing CHANGELOG → simply omitted (returns
  whatever exists; never raises for absent files).

### `src/crypto_predictor/ui/pages/journal.py` (thin)

- `require_auth()` (same as other pages).
- `st.title("📓 Journal")`, short caption.
- Resolve project root from the page file: `journal.py` lives at
  `src/crypto_predictor/ui/pages/`, so `Path(__file__).resolve().parents[4]`
  is the repo root. (The app also runs with `WorkingDirectory=/opt/crypto-predictor`,
  so a relative `Path("docs/sessions")` would work too — but parents[4] is
  independent of cwd and matches how other modules resolve.)
- `entries = load_log_entries(root)` wrapped in `@st.cache_data(ttl=300)`.
- For each entry, render `st.expander(entry.label, expanded=<first entry only>)`
  containing `st.markdown(entry.body)`.
- Empty list → `st.info("No journal entries found.")`.

### Navigation

Add as the 5th `st.Page` in `app.py`, after Track Record:
`st.Page("pages/journal.py", title="Journal", icon="📓")`.

## Data flow

Markdown files live in the git checkout; refreshed on deploy (`git pull`). The
loader reads them at page load (5-min cache). No DB, no write path.

## Decisions

- Newest journal expanded by default; older journals + CHANGELOG collapsed.
- CHANGELOG pinned as the last entry (it is not a single dated session).
- **Auth/sensitivity:** behind the existing nginx basic-auth (single user). The
  journals contain server internals (IP, ops detail); acceptable because the
  page is never public. If the site is ever opened up, this page must be gated
  or the journals redacted — noted as a constraint, not built now.

## Testing (TDD)

`journal_loader` unit tests:
- newest-first ordering across multiple dated files
- title extracted from the first `# H1`; falls back to filename stem
- non-date-prefixed files skipped
- CHANGELOG appended last when present; omitted when absent
- missing `docs/sessions/` dir → no raise, returns (changelog only / empty)

Page is thin; covered by an import/smoke check (the existing UI test pattern).

## Out of scope (YAGNI)

Search, §section-level splitting, in-UI editing, pagination, public access,
rendering specs/plans (only sessions journals + CHANGELOG).
