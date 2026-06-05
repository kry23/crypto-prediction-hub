"""Server-side Claude assistant tools — read project DB / files.

Each function returns a JSON-serializable dict / list so the Anthropic
`tool_use` loop can hand the value straight back to the model as the
`tool_result` content.

The tools are *deliberately* read-only and project-scoped:

    1. ``query_predictions``             — PG ``predictions`` slice
    2. ``query_completeness_breakdown``  — PG aggregate by completeness
    3. ``query_calibration_state``       — ``data/calibration_<v>.json`` read
    4. ``run_ship_criteria_check``       — subprocess ``scripts/ship_criteria_check.py``
    5. ``query_intel_hub``               — PG ``whale_txs`` + ``news_feed``
    6. ``read_journal``                  — grep on ``docs/sessions/*.md``

Module also exports ``TOOL_SCHEMAS`` — the Anthropic ``tools=[...]`` payload
matching these six functions, plus ``TOOL_DISPATCH``, the name→callable
map used by :mod:`crypto_predictor.ui.claude_session` to execute a
``tool_use`` block returned by the model.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# 1. predictions slice
# ---------------------------------------------------------------------------

_ALLOWED_EQ_FILTERS = (
    "symbol",
    "status",
    "mode",
    "regime",
    "confidence_flag",
    "feature_completeness",
)

_PREDICTION_COLUMNS = (
    "id", "symbol", "prediction", "p_direction", "target_value",
    "composite_score", "confidence_flag", "regime", "mode", "status",
    "feature_completeness", "created_at",
)


def query_predictions(
    *,
    conn,
    filters: dict[str, Any] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return up to ``limit`` predictions matching ``filters``.

    Allowed filter keys: ``symbol``, ``status``, ``mode``, ``regime``,
    ``confidence_flag``, ``feature_completeness`` (equality match) and
    ``since`` (ISO timestamp; rows with ``created_at >= since`` only).
    Unknown keys are silently ignored.
    """
    filters = filters or {}
    where = ["1 = 1"]
    params: list[Any] = []
    for col in _ALLOWED_EQ_FILTERS:
        if col in filters and filters[col] is not None:
            where.append(f"{col} = %s")
            params.append(filters[col])
    if filters.get("since") is not None:
        where.append("created_at >= %s")
        params.append(filters["since"])
    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        limit_int = 50
    limit_int = max(1, min(limit_int, 500))
    sql = (
        "SELECT id, symbol, prediction, p_direction, target_value, "
        "       composite_score, confidence_flag, regime, mode, status, "
        "       feature_completeness, created_at "
        "FROM predictions "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC LIMIT %s"
    )
    params.append(limit_int)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        cols = [d.name for d in cur.description]
        out: list[dict] = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            # Cast Decimals/datetimes to JSON-friendly primitives.
            for k, v in list(d.items()):
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
                elif hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
                    try:
                        d[k] = float(v)
                    except (TypeError, ValueError):
                        d[k] = str(v)
            out.append(d)
        return out


# ---------------------------------------------------------------------------
# 2. completeness breakdown
# ---------------------------------------------------------------------------

def query_completeness_breakdown(
    *,
    conn,
    window_days: int = 7,
    mode: str = "shadow",
) -> dict:
    """Aggregate closed predictions by ``feature_completeness`` over the
    last ``window_days``.

    Returns ``{completeness_label: {n, n_correct, hit_rate}}``.
    Buckets with no closures appear with ``n=0`` and ``hit_rate=0.0``.
    """
    try:
        window = max(1, int(window_days))
    except (TypeError, ValueError):
        window = 7

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT feature_completeness,
                   COUNT(*) AS n,
                   SUM(CASE WHEN status = 'correct' THEN 1 ELSE 0 END) AS n_correct
            FROM predictions
            WHERE mode = %s
              AND status IN ('correct', 'incorrect')
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            GROUP BY feature_completeness
            """,
            (mode, window),
        )
        rows = cur.fetchall()

    out: dict[str, dict] = {}
    for completeness, n, n_correct in rows:
        n_int = int(n) if n is not None else 0
        n_correct_int = int(n_correct) if n_correct is not None else 0
        hit_rate = n_correct_int / n_int if n_int else 0.0
        key = completeness or "unknown"
        out[key] = {
            "n": n_int,
            "n_correct": n_correct_int,
            "hit_rate": float(hit_rate),
        }
    return {
        "window_days": window,
        "mode": mode,
        "by_completeness": out,
    }


# ---------------------------------------------------------------------------
# 3. calibration state
# ---------------------------------------------------------------------------

def _active_calibration_version() -> str | None:
    """Read ``data/scheduler_config.yaml`` for the active calibration version."""
    cfg_path = PROJECT_ROOT / "data" / "scheduler_config.yaml"
    if not cfg_path.exists():
        return None
    try:
        with cfg_path.open("r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None
    version = cfg.get("calibration_version")
    if version is None:
        return None
    return str(version)


def query_calibration_state(version: str | None = None) -> dict:
    """Inspect ``data/calibration_<version>.json``.

    When ``version`` is ``None`` reads ``data/scheduler_config.yaml`` to find
    the active version. Detects two on-disk shapes:

    * ``legacy``           — top-level ``{"regimes": {...}}`` keyed by regime
    * ``per_completeness`` — top-level ``{"per_completeness": {...}}`` or
                             ``{"full": {...}, "degraded": {...}}``

    Returns
    -------
    dict with ``version``, ``format`` (``legacy`` | ``per_completeness`` |
    ``unknown`` | ``missing``), ``keys`` (regimes or completeness labels),
    ``knot_counts`` (per-key length of ``x``), ``ceilings`` (per-key
    ``max(y)``), and ``path``.
    """
    if version is None:
        version = _active_calibration_version()
    if version is None:
        return {
            "version": None,
            "format": "missing",
            "keys": [],
            "knot_counts": {},
            "ceilings": {},
            "path": None,
            "error": "no active calibration version (scheduler_config.yaml missing or malformed)",
        }

    path = PROJECT_ROOT / "data" / f"calibration_{version}.json"
    if not path.exists():
        return {
            "version": version,
            "format": "missing",
            "keys": [],
            "knot_counts": {},
            "ceilings": {},
            "path": str(path),
            "error": f"file not found: {path.name}",
        }

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "version": version,
            "format": "unknown",
            "keys": [],
            "knot_counts": {},
            "ceilings": {},
            "path": str(path),
            "error": f"read/parse failure: {exc}",
        }

    if isinstance(data, dict) and "regimes" in data:
        bucket: dict[str, Any] = data["regimes"]
        fmt = "legacy"
    elif isinstance(data, dict) and "per_completeness" in data:
        bucket = data["per_completeness"]
        fmt = "per_completeness"
    elif isinstance(data, dict) and {"full", "degraded"} & set(data.keys()):
        bucket = {k: data[k] for k in ("full", "degraded") if k in data}
        fmt = "per_completeness"
    else:
        return {
            "version": version,
            "format": "unknown",
            "keys": list(data.keys()) if isinstance(data, dict) else [],
            "knot_counts": {},
            "ceilings": {},
            "path": str(path),
            "fit_window": data.get("fit_window") if isinstance(data, dict) else None,
        }

    knot_counts: dict[str, int] = {}
    ceilings: dict[str, float] = {}
    for key, entry in bucket.items():
        if not isinstance(entry, dict):
            continue
        xs = entry.get("x") or []
        ys = entry.get("y") or []
        knot_counts[key] = len(xs)
        if ys:
            try:
                ceilings[key] = float(max(ys))
            except (TypeError, ValueError):
                pass

    return {
        "version": version,
        "format": fmt,
        "keys": list(bucket.keys()),
        "knot_counts": knot_counts,
        "ceilings": ceilings,
        "path": str(path),
        "fit_window": data.get("fit_window") if isinstance(data, dict) else None,
    }


# ---------------------------------------------------------------------------
# 4. ship_criteria_check subprocess
# ---------------------------------------------------------------------------

def run_ship_criteria_check(*, timeout_s: int = 60) -> dict:
    """Run ``scripts/ship_criteria_check.py`` and parse the output.

    Returns dict with ``can_ship`` (bool), ``exit_code`` (int), ``headline``
    (raw line), ``buckets`` (list of best-effort parsed bucket lines), and
    ``raw_output`` (full stdout+stderr). Always returns rather than raising —
    the model needs the failure surfaced.
    """
    script = PROJECT_ROOT / "scripts" / "ship_criteria_check.py"
    if not script.exists():
        return {
            "can_ship": False,
            "exit_code": -1,
            "headline": "",
            "buckets": [],
            "raw_output": f"script not found: {script}",
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {
            "can_ship": False,
            "exit_code": -2,
            "headline": "",
            "buckets": [],
            "raw_output": f"timeout after {timeout_s}s",
        }
    except OSError as exc:
        return {
            "can_ship": False,
            "exit_code": -3,
            "headline": "",
            "buckets": [],
            "raw_output": f"OSError: {exc}",
        }

    raw = (proc.stdout or "") + (proc.stderr or "")
    headline = ""
    buckets: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if not headline and ("hit_rate" in lower or "brier" in lower):
            headline = stripped
        if "bucket" in lower or re.match(r"\[?0\.\d{2}\s*[-,]", stripped):
            buckets.append(stripped)

    return {
        "can_ship": proc.returncode == 0,
        "exit_code": proc.returncode,
        "headline": headline,
        "buckets": buckets,
        "raw_output": raw,
    }


# ---------------------------------------------------------------------------
# 5. intel-hub (whale + news)
# ---------------------------------------------------------------------------

def query_intel_hub(
    *,
    conn,
    category: str | None = None,
    hours_back: int = 24,
    limit: int = 100,
) -> list[dict]:
    """Return whale TXs + news items from the last ``hours_back`` hours.

    Each row is annotated with ``source='whale'`` or ``source='news'``.
    If ``category`` is given, only news with that ``category`` are returned
    (whale rows are always returned regardless of ``category`` since they
    don't carry one).
    """
    try:
        hours = max(1, int(hours_back))
    except (TypeError, ValueError):
        hours = 24
    try:
        limit_int = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit_int = 100

    out: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, chain, symbol, tx_hash, amount_usd,
                   from_label, to_label, ts
            FROM whale_txs
            WHERE ts >= (now() AT TIME ZONE 'UTC')
                          - make_interval(hours => %s)
            ORDER BY ts DESC
            LIMIT %s
            """,
            (hours, limit_int),
        )
        for row in cur.fetchall():
            d = dict(zip(
                ("id", "chain", "symbol", "tx_hash", "amount_usd",
                 "from_label", "to_label", "ts"), row,
            ))
            if isinstance(d.get("ts"), datetime):
                d["ts"] = d["ts"].isoformat()
            if d.get("amount_usd") is not None:
                try:
                    d["amount_usd"] = float(d["amount_usd"])
                except (TypeError, ValueError):
                    pass
            d["source"] = "whale"
            out.append(d)

        if category is not None:
            cur.execute(
                """
                SELECT id, category, severity, title, url, source,
                       symbols_mentioned, sentiment, ts
                FROM news_feed
                WHERE ts >= (now() AT TIME ZONE 'UTC')
                              - make_interval(hours => %s)
                  AND category = %s
                ORDER BY ts DESC
                LIMIT %s
                """,
                (hours, category, limit_int),
            )
        else:
            cur.execute(
                """
                SELECT id, category, severity, title, url, source,
                       symbols_mentioned, sentiment, ts
                FROM news_feed
                WHERE ts >= (now() AT TIME ZONE 'UTC')
                              - make_interval(hours => %s)
                ORDER BY ts DESC
                LIMIT %s
                """,
                (hours, limit_int),
            )
        for row in cur.fetchall():
            d = dict(zip(
                ("id", "category", "severity", "title", "url", "feed_source",
                 "symbols_mentioned", "sentiment", "ts"), row,
            ))
            if isinstance(d.get("ts"), datetime):
                d["ts"] = d["ts"].isoformat()
            if d.get("sentiment") is not None:
                try:
                    d["sentiment"] = float(d["sentiment"])
                except (TypeError, ValueError):
                    pass
            d["source"] = "news"
            out.append(d)

    return out


# ---------------------------------------------------------------------------
# 6. read_journal
# ---------------------------------------------------------------------------

_JOURNAL_HEADER = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _most_recent_journal(journal_dir: Path) -> Path | None:
    candidates = sorted(journal_dir.glob("*.md"))
    if not candidates:
        return None
    # File names are ISO-prefixed (YYYY-MM-DD-*), so lexicographic == chrono.
    return candidates[-1]


def read_journal(
    *,
    section_regex: str = ".*",
    journal_path: Path | None = None,
    max_bytes: int = 8000,
) -> str:
    """grep-style read of the session journal.

    Walks the journal as markdown sections (header → body) and returns the
    concatenation of every section whose header matches ``section_regex``.
    Defaults to the most recent file under ``docs/sessions/``.
    Output is truncated to ``max_bytes`` UTF-8 chars to keep the model's
    context fed but bounded.
    """
    if journal_path is None:
        journal_dir = PROJECT_ROOT / "docs" / "sessions"
        if not journal_dir.exists():
            return ""
        journal_path = _most_recent_journal(journal_dir)
        if journal_path is None:
            return ""

    try:
        text = Path(journal_path).read_text(encoding="utf-8")
    except OSError:
        return ""

    try:
        pattern = re.compile(section_regex, flags=re.IGNORECASE)
    except re.error:
        return ""

    sections: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        m = _JOURNAL_HEADER.match(line)
        if m:
            if current_header is not None:
                sections.append((current_header, current_body))
            current_header = line
            current_body = []
        else:
            current_body.append(line)
    if current_header is not None:
        sections.append((current_header, current_body))

    selected: list[str] = []
    for header, body in sections:
        if pattern.search(header):
            selected.append(header)
            selected.extend(body)

    out = "\n".join(selected).strip()
    if len(out) > max_bytes:
        out = out[:max_bytes] + "\n... [truncated]"
    return out


# ---------------------------------------------------------------------------
# Anthropic tool schemas (JSON schema per Anthropic tool_use spec)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "query_predictions",
        "description": (
            "Query the predictions table. Filter by symbol, status, mode, "
            "regime, confidence_flag, feature_completeness, or since "
            "(ISO timestamp). Returns up to `limit` rows ordered by "
            "created_at DESC."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": (
                        "Equality filters. Allowed keys: symbol, status, "
                        "mode, regime, confidence_flag, "
                        "feature_completeness, since."
                    ),
                    "additionalProperties": True,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                },
            },
        },
    },
    {
        "name": "query_completeness_breakdown",
        "description": (
            "Aggregate closed predictions by feature_completeness "
            "(full|degraded) over the rolling window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_days": {"type": "integer", "minimum": 1,
                                "default": 7},
                "mode": {"type": "string", "default": "shadow"},
            },
        },
    },
    {
        "name": "query_calibration_state",
        "description": (
            "Inspect the active (or specified) calibration JSON. Returns "
            "format, regime/completeness keys, knot counts and ceilings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "version": {
                    "type": ["string", "null"],
                    "description": (
                        "Calibration version (e.g. '1_5_4'). When omitted "
                        "uses the version active in scheduler_config.yaml."
                    ),
                },
            },
        },
    },
    {
        "name": "run_ship_criteria_check",
        "description": (
            "Run scripts/ship_criteria_check.py and return its structured "
            "headline + per-bucket output plus exit code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout_s": {"type": "integer", "minimum": 5,
                              "maximum": 300, "default": 60},
            },
        },
    },
    {
        "name": "query_intel_hub",
        "description": (
            "Whale TXs + news items in the last hours_back hours. "
            "If category is given the news side filters by category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": ["string", "null"]},
                "hours_back": {"type": "integer", "minimum": 1,
                               "maximum": 168, "default": 24},
                "limit": {"type": "integer", "minimum": 1,
                          "maximum": 500, "default": 100},
            },
        },
    },
    {
        "name": "read_journal",
        "description": (
            "Read sections from the most recent session journal that match "
            "section_regex (case-insensitive). Default reads everything; "
            "scope by passing a heading-like regex."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_regex": {"type": "string", "default": ".*"},
            },
        },
    },
]


# Name -> callable. The caller injects ``conn`` (and other infra deps) by
# wrapping the bare callable; see ``claude_session.dispatch_tool``.
TOOL_DISPATCH: dict[str, Callable[..., Any]] = {
    "query_predictions": query_predictions,
    "query_completeness_breakdown": query_completeness_breakdown,
    "query_calibration_state": query_calibration_state,
    "run_ship_criteria_check": run_ship_criteria_check,
    "query_intel_hub": query_intel_hub,
    "read_journal": read_journal,
}

# Subset that needs the PG connection injected.
TOOLS_NEEDING_CONN: frozenset[str] = frozenset({
    "query_predictions",
    "query_completeness_breakdown",
    "query_intel_hub",
})
