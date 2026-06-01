# crypto-predictor Phase 1 — Plan A: Foundation (Weeks 1–3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data foundation — plugin scaffold, bulk historical ingest of 6 months of OKX-Global perp data into Parquet, and a fully-tested feature pipeline producing ~30 z-scored features per coin.

**Architecture:** Single-plugin Python project at `C:\Users\Koray\Desktop\crypto-predictor\`, layered as: (1) plugin manifest + scheduler skeleton, (2) parquet-backed historical store with idempotent ingest, (3) modular feature library composed of six families (momentum, perp microstructure, volume, technical, sentiment, global) gated by a strict `asof`-guard fetcher to prevent look-ahead bias.

**Tech Stack:** Python 3.12 + uv (env mgmt), FastMCP (MCP server), APScheduler (jobs), SQLite (state), Parquet via pyarrow (history), ccxt (OKX), pandas + numpy (features), pytest (tests), structlog (logging).

**Related docs:**
- Design spec: [`docs/design/2026-06-01-crypto-predictor-design.md`](../design/2026-06-01-crypto-predictor-design.md)
- Sibling plugins to study: `~/.claude/plugins/crypto-intel-hub/`, `~/.claude/plugins/cache/hugoguerrap/crypto-trading-desk/1.0.0/`

**Plan A success criteria:**
- `compute_features("BTCUSDT", asof=datetime.utcnow())` returns ~30 features in <500ms.
- Look-ahead guard test passes (FeatureFetcher refuses data ≥ asof).
- Bulk-ingest parquet covers 340 perps × 6 months × 4 timeframes + funding/OI/L-S/liquidation series.
- `/predict ping` slash command works.
- All Plan A unit tests green; ≥30 tests.

---

## Navigation

- **Week 1 — Plugin Foundation** (10 tasks)
- **Week 2 — Bulk Historical Ingest** (8 tasks)
- **Week 3 — Feature Pipeline** (12 tasks)
- **Plan A complete — handoff to Plan B**

---

## Prerequisites (before Task 1.1)

- [ ] **Verify required tools**

Run in PowerShell:
```powershell
python --version    # expect 3.12+
uv --version        # expect 0.4+
git --version       # any recent
```

Expected: all three print a version. If `uv` missing: `pip install uv`. If `git` missing: install from git-scm.com.

- [ ] **Verify Desktop project root exists with design doc**

```powershell
Test-Path "C:\Users\Koray\Desktop\crypto-predictor\docs\design\2026-06-01-crypto-predictor-design.md"
```

Expected: `True`. (This was created during brainstorming.)

- [ ] **Confirm GitHub repo accessible**

Open https://github.com/kry23/crypto-prediction-hub in browser. Should be empty repo (no README) or with one initial commit.

> **Naming note**: local folder is `crypto-predictor`, remote repo is `crypto-prediction-hub`. Both names are kept — local path stays short, remote name describes the product. Git tracks remote URL, not folder name, so this is fine.

---

# Week 1 — Plugin Foundation

Goal: blank plugin scaffold that registers with Claude Code and responds to `/predict ping`.

## Task 1.1: Project bootstrap (uv venv + pyproject)

**Files:**
- Create: `C:\Users\Koray\Desktop\crypto-predictor\pyproject.toml`
- Create: `C:\Users\Koray\Desktop\crypto-predictor\.gitignore`
- Create: `C:\Users\Koray\Desktop\crypto-predictor\.python-version`
- Create: `C:\Users\Koray\Desktop\crypto-predictor\src\crypto_predictor\__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "crypto-predictor"
version = "0.1.0"
description = "Heuristic-first probabilistic prediction platform for OKX-Global USDT perpetuals."
authors = [{name = "Koray Korkmaz"}]
license = {text = "MIT"}
requires-python = ">=3.12"
readme = "README.md"
dependencies = [
    "fastmcp>=0.2.0",
    "apscheduler>=3.10.0",
    "ccxt>=4.4.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "pyarrow>=15.0.0",
    "scikit-learn>=1.4.0",
    "scipy>=1.12.0",
    "structlog>=24.1.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
    "pyyaml>=6.0.1",
    "tenacity>=8.2.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.4.0",
    "mypy>=1.9.0",
    "freezegun>=1.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/crypto_predictor"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4"]
```

- [ ] **Step 2: Create .python-version**

```
3.12
```

- [ ] **Step 3: Create .gitignore**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db
desktop.ini

# Editor
.vscode/
.idea/

# Project data (large/regenerable)
data/history/
data/db/
*.parquet
*.db
*.db-journal

# Secrets
.env
secrets.env
*.secret

# Reports (gitignored, generated daily)
reports/
```

- [ ] **Step 4: Create src package skeleton**

```python
# src/crypto_predictor/__init__.py
"""crypto-predictor — heuristic-first crypto prediction platform."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Initialize uv environment and install**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
uv venv
uv pip install -e ".[dev]"
```

Expected: `.venv\` folder created, all dependencies install without errors.

- [ ] **Step 6: Verify package importable**

```powershell
.\.venv\Scripts\python.exe -c "import crypto_predictor; print(crypto_predictor.__version__)"
```

Expected output: `0.1.0`

- [ ] **Step 7: Save state — no commit yet (git init is Task 1.2)**

---

## Task 1.2: Git init + GitHub remote + initial commit

**Files:** none new (repo metadata)

- [ ] **Step 1: Initialize git repo**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
git init
git branch -M main
```

Expected: `Initialized empty Git repository in C:/Users/Koray/Desktop/crypto-predictor/.git/`

- [ ] **Step 2: Add GitHub remote**

```powershell
git remote add origin https://github.com/kry23/crypto-prediction-hub.git
git remote -v
```

Expected: both fetch+push lines pointing to the GitHub URL.

- [ ] **Step 3: Stage Plan A scaffold**

```powershell
git add pyproject.toml .gitignore .python-version src/ docs/
git status
```

Expected: design doc, plan doc, pyproject, gitignore, python-version, src package — all staged.

- [ ] **Step 4: Initial commit**

```powershell
git commit -m "chore: bootstrap crypto-predictor project scaffold"
```

Expected: commit succeeds with files listed.

- [ ] **Step 5: Push to GitHub**

```powershell
git push -u origin main
```

Expected: push succeeds. If GitHub repo had initial README, may need `git pull --rebase origin main` first; then push.

---

## Task 1.3: Plugin manifest

**Files:**
- Create: `C:\Users\Koray\Desktop\crypto-predictor\.claude-plugin\plugin.json`

- [ ] **Step 1: Create plugin manifest**

```json
{
  "name": "crypto-predictor",
  "version": "0.1.0",
  "description": "Heuristic-first probabilistic prediction for OKX-Global USDT perpetuals — daily universe scan, calibrated direction + magnitude predictions, self-validating track record.",
  "author": {
    "name": "Koray Korkmaz"
  },
  "license": "MIT",
  "mcpServers": {
    "crypto-predictor": {
      "command": "${CLAUDE_PLUGIN_ROOT}/.venv/Scripts/python.exe",
      "args": ["${CLAUDE_PLUGIN_ROOT}/src/crypto_predictor/mcp/server.py"]
    }
  }
}
```

- [ ] **Step 2: Validate JSON**

```powershell
.\.venv\Scripts\python.exe -c "import json; json.load(open('.claude-plugin/plugin.json'))"
```

Expected: no output, no error → valid JSON.

- [ ] **Step 3: Commit**

```powershell
git add .claude-plugin/plugin.json
git commit -m "chore: add plugin manifest"
git push
```

---

## Task 1.4: Predictions DB schema module

**Files:**
- Create: `src/crypto_predictor/storage/__init__.py`
- Create: `src/crypto_predictor/storage/predictions_db.py`
- Create: `tests/storage/__init__.py`
- Create: `tests/storage/test_predictions_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_predictions_db.py
from pathlib import Path

import pytest

from crypto_predictor.storage.predictions_db import init_db, get_table_names


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "predictions.db"


def test_init_creates_all_tables(tmp_db: Path):
    init_db(tmp_db)
    tables = get_table_names(tmp_db)
    expected = {
        "predictions",
        "predictions_features",
        "calibration_maps",
        "regime_log",
        "metrics_rolling",
        "patterns",
        "runs",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_init_is_idempotent(tmp_db: Path):
    init_db(tmp_db)
    init_db(tmp_db)  # second call must not raise
    assert get_table_names(tmp_db)


def test_predictions_has_expected_columns(tmp_db: Path):
    import sqlite3
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    expected = {
        "id", "symbol", "horizon_hours", "prediction", "p_direction",
        "target_value", "composite_score", "confidence_flag", "regime",
        "formula_version", "calibration_version", "status", "actual_outcome",
        "error_margin", "evaluation", "created_at", "validated_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"
    conn.close()
```

- [ ] **Step 2: Run test, verify FAIL**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/storage/test_predictions_db.py -v
```

Expected: ModuleNotFoundError for `crypto_predictor.storage.predictions_db`.

- [ ] **Step 3: Implement minimal module**

```python
# src/crypto_predictor/storage/__init__.py
"""Storage layer — SQLite + parquet."""
```

```python
# src/crypto_predictor/storage/predictions_db.py
"""predictions.db — own schema for crypto-predictor (separate from learning-db)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                  TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    horizon_hours       INTEGER NOT NULL DEFAULT 24,
    prediction          TEXT NOT NULL CHECK (prediction IN ('up','down')),
    p_direction         REAL NOT NULL,
    target_value        REAL NOT NULL,
    composite_score     REAL NOT NULL,
    confidence_flag     TEXT CHECK (confidence_flag IN ('NORMAL','HIGH_CONV','WILD_CARD')),
    regime              TEXT NOT NULL CHECK (regime IN ('BULL','BEAR','CHOP')),
    formula_version     TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','correct','incorrect','expired','skipped')),
    actual_outcome      REAL,
    error_margin        REAL,
    evaluation          TEXT,
    created_at          TEXT NOT NULL,
    validated_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_symbol  ON predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_pred_status  ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_pred_created ON predictions(created_at);
CREATE INDEX IF NOT EXISTS idx_pred_regime  ON predictions(regime);

CREATE TABLE IF NOT EXISTS predictions_features (
    prediction_id TEXT NOT NULL,
    feature_name  TEXT NOT NULL,
    raw_value     REAL,
    z_value       REAL,
    PRIMARY KEY (prediction_id, feature_name),
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

CREATE TABLE IF NOT EXISTS calibration_maps (
    version    TEXT NOT NULL,
    regime     TEXT NOT NULL,
    map_json   TEXT NOT NULL,
    fit_window TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (version, regime)
);

CREATE TABLE IF NOT EXISTS regime_log (
    date              TEXT PRIMARY KEY,
    regime            TEXT NOT NULL,
    btc_30d_return    REAL,
    btc_funding_avg   REAL,
    global_mcap_trend REAL
);

CREATE TABLE IF NOT EXISTS metrics_rolling (
    window         TEXT,
    regime         TEXT,
    direction      TEXT,
    n_predictions  INTEGER,
    n_correct      INTEGER,
    hit_rate       REAL,
    mae            REAL,
    brier          REAL,
    topk_alpha     REAL,
    topk_alpha_btc REAL,
    updated_at     TEXT,
    PRIMARY KEY (window, regime, direction)
);

CREATE TABLE IF NOT EXISTS patterns (
    name            TEXT PRIMARY KEY,
    conditions      TEXT,
    occurrences     INTEGER NOT NULL DEFAULT 0,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    win_rate        REAL NOT NULL DEFAULT 0,
    avg_pnl_percent REAL NOT NULL DEFAULT 0,
    first_seen      TEXT,
    last_seen       TEXT,
    recommendation  TEXT CHECK (recommendation IN ('SEEK','NEUTRAL','AVOID')),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    job                 TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT CHECK (status IN ('ok','error','partial')),
    n_predictions       INTEGER,
    n_errors            INTEGER,
    error_summary       TEXT,
    formula_version     TEXT,
    calibration_version TEXT
);
"""


def init_db(path: Path) -> None:
    """Create predictions.db schema if missing. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_table_names(path: Path) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/storage/test_predictions_db.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/storage/ tests/storage/
git commit -m "feat(storage): predictions.db schema with 7 tables + idempotent init"
git push
```

---

## Task 1.5: Features DB schema module

**Files:**
- Create: `src/crypto_predictor/storage/features_db.py`
- Create: `tests/storage/test_features_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_features_db.py
from pathlib import Path

import pytest

from crypto_predictor.storage.features_db import init_db, write_snapshot, read_snapshot


def test_init_creates_feature_snapshot_table(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "feature_snapshot" in tables
    conn.close()


def test_write_and_read_roundtrip(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    write_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z",
                   {"ret_1h_z": 0.5, "funding_z": -1.2})
    out = read_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z")
    assert out == {"ret_1h_z": 0.5, "funding_z": -1.2}


def test_read_returns_empty_when_missing(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    assert read_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z") == {}
```

- [ ] **Step 2: Run test, verify FAIL**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/storage/test_features_db.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement module**

```python
# src/crypto_predictor/storage/features_db.py
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
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/storage/test_features_db.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/storage/features_db.py tests/storage/test_features_db.py
git commit -m "feat(storage): features.db with snapshot read/write roundtrip"
git push
```

---

## Task 1.6: FastMCP server skeleton + ping tool

**Files:**
- Create: `src/crypto_predictor/mcp/__init__.py`
- Create: `src/crypto_predictor/mcp/server.py`
- Create: `tests/mcp/__init__.py`
- Create: `tests/mcp/test_server_ping.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_server_ping.py
from crypto_predictor.mcp.server import ping


def test_ping_returns_status_ok():
    result = ping()
    assert result["status"] == "ok"
    assert "version" in result
    assert "timestamp" in result
```

- [ ] **Step 2: Run test, verify FAIL**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/mcp/test_server_ping.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement MCP server with ping**

```python
# src/crypto_predictor/mcp/__init__.py
"""MCP server for crypto-predictor."""
```

```python
# src/crypto_predictor/mcp/server.py
"""crypto-predictor FastMCP server — entry point for MCP tools."""
from __future__ import annotations

from datetime import datetime, timezone

from fastmcp import FastMCP

from crypto_predictor import __version__

mcp = FastMCP("crypto-predictor")


@mcp.tool()
def ping() -> dict:
    """Health check — returns server status, version, and current UTC timestamp."""
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/mcp/test_server_ping.py -v
```

Expected: 1 test passes.

- [ ] **Step 5: Manual MCP smoke test**

```powershell
.\.venv\Scripts\python.exe -c "from crypto_predictor.mcp.server import ping; print(ping())"
```

Expected: dict with status=ok, version=0.1.0, timestamp in ISO format.

- [ ] **Step 6: Commit**

```powershell
git add src/crypto_predictor/mcp/ tests/mcp/
git commit -m "feat(mcp): FastMCP server with ping health check"
git push
```

---

## Task 1.7: Scheduler skeleton

**Files:**
- Create: `src/crypto_predictor/scheduler/__init__.py`
- Create: `src/crypto_predictor/scheduler/jobs.py`
- Create: `tests/scheduler/__init__.py`
- Create: `tests/scheduler/test_scheduler_skeleton.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scheduler/test_scheduler_skeleton.py
from crypto_predictor.scheduler.jobs import build_scheduler, list_registered_jobs


def test_scheduler_has_four_jobs():
    sched = build_scheduler()
    names = list_registered_jobs(sched)
    assert "predict_scan" in names
    assert "validate_pending" in names
    assert "weekly_metrics" in names
    assert "recalibrate" in names
    sched.shutdown(wait=False)


def test_scheduler_jobs_have_correct_cron():
    from apscheduler.triggers.cron import CronTrigger
    sched = build_scheduler()
    by_name = {job.id: job for job in sched.get_jobs()}
    # predict_scan: daily 06:00 UTC
    trig = by_name["predict_scan"].trigger
    assert isinstance(trig, CronTrigger)
    fields = {f.name: str(f) for f in trig.fields}
    assert fields["hour"] == "6"
    assert fields["minute"] == "0"
    sched.shutdown(wait=False)
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement scheduler skeleton with no-op jobs**

```python
# src/crypto_predictor/scheduler/__init__.py
"""APScheduler-based job runner."""
```

```python
# src/crypto_predictor/scheduler/jobs.py
"""Cron job registry — defines schedule, jobs are no-ops in Plan A."""
from __future__ import annotations

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = structlog.get_logger(__name__)


def _job_predict_scan() -> None:
    log.info("predict_scan job fired (no-op in Plan A)")


def _job_validate_pending() -> None:
    log.info("validate_pending job fired (no-op in Plan A)")


def _job_weekly_metrics() -> None:
    log.info("weekly_metrics job fired (no-op in Plan A)")


def _job_recalibrate() -> None:
    log.info("recalibrate job fired (no-op in Plan A)")


def build_scheduler() -> BackgroundScheduler:
    """Build scheduler with all four Phase-1 jobs registered (no-ops until later plans)."""
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_job_predict_scan,
                  CronTrigger(hour=6, minute=0), id="predict_scan", replace_existing=True)
    sched.add_job(_job_validate_pending,
                  CronTrigger(hour=6, minute=30), id="validate_pending", replace_existing=True)
    sched.add_job(_job_weekly_metrics,
                  CronTrigger(day_of_week="sun", hour=7, minute=0), id="weekly_metrics",
                  replace_existing=True)
    sched.add_job(_job_recalibrate,
                  CronTrigger(day=1, hour=7, minute=0), id="recalibrate",
                  replace_existing=True)
    return sched


def list_registered_jobs(sched: BackgroundScheduler) -> list[str]:
    return [job.id for job in sched.get_jobs()]
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/scheduler/ -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/scheduler/ tests/scheduler/
git commit -m "feat(scheduler): APScheduler skeleton with 4 cron jobs (no-op stubs)"
git push
```

---

## Task 1.8: Structured logging configuration

**Files:**
- Create: `src/crypto_predictor/logging_config.py`
- Create: `tests/test_logging_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logging_config.py
import json
import logging

from crypto_predictor.logging_config import configure_logging


def test_configure_logging_emits_json(capsys):
    configure_logging(level="INFO")
    log = logging.getLogger("crypto_predictor.test")
    log.info("hello", extra={"foo": "bar"})
    captured = capsys.readouterr()
    # stdout should have a JSON line
    line = captured.err.strip().split("\n")[-1] if captured.err else captured.out.strip().split("\n")[-1]
    data = json.loads(line)
    assert data["event"] == "hello"
    assert data["level"] == "info"
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement logging configuration**

```python
# src/crypto_predictor/logging_config.py
"""Structured JSON logging via structlog."""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit JSON lines to stdout."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_logging_config.py -v
```

Expected: 1 test passes (note: structlog routes through stdlib; if the assertion fails, adjust capsys capture target — but most cases pass on first run).

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/logging_config.py tests/test_logging_config.py
git commit -m "feat(logging): structlog JSON configuration with timestamp"
git push
```

---

## Task 1.9: Secrets loader

**Files:**
- Create: `src/crypto_predictor/config.py`
- Create: `data/secrets.env.example`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from crypto_predictor.config import load_secrets, MissingSecretError


def test_load_secrets_reads_env_file(tmp_path: Path):
    env = tmp_path / "secrets.env"
    env.write_text("FOO=bar\nBAZ=qux\n")
    secrets = load_secrets(env)
    assert secrets["FOO"] == "bar"
    assert secrets["BAZ"] == "qux"


def test_load_secrets_strips_quotes(tmp_path: Path):
    env = tmp_path / "secrets.env"
    env.write_text('TOKEN="abc123"\n')
    assert load_secrets(env)["TOKEN"] == "abc123"


def test_load_secrets_missing_file_returns_empty(tmp_path: Path):
    assert load_secrets(tmp_path / "missing.env") == {}


def test_require_secret_raises_when_absent():
    from crypto_predictor.config import require_secret
    with pytest.raises(MissingSecretError):
        require_secret({}, "TELEGRAM_BOT_TOKEN")
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement config module**

```python
# src/crypto_predictor/config.py
"""Configuration + secrets loader (intel-hub pattern)."""
from __future__ import annotations

from pathlib import Path


class MissingSecretError(KeyError):
    """Raised when a required secret is not present in the loaded env."""


def load_secrets(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from a dotenv-style file. Missing file → empty dict."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def require_secret(secrets: dict[str, str], name: str) -> str:
    """Return secret value or raise MissingSecretError."""
    if name not in secrets or not secrets[name]:
        raise MissingSecretError(f"required secret '{name}' is missing")
    return secrets[name]
```

- [ ] **Step 4: Create secrets template**

```
# data/secrets.env.example
# Copy to data/secrets.env and fill in real values.
# NEVER commit secrets.env — it is gitignored.

# OKX (public data only — no API key needed for read endpoints)
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=

# Telegram (reuse from crypto-intel-hub)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# News sources
NEWSAPI_API_KEY=

# LunarCrush (Tier 2 social sentiment)
LUNARCRUSH_API_KEY=

# Anthropic (for LLM summaries — uses your existing Claude Code session by default)
ANTHROPIC_API_KEY=
```

- [ ] **Step 5: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Create actual secrets file (manual, no commit)**

```powershell
Copy-Item data/secrets.env.example data/secrets.env
notepad data/secrets.env  # fill in real values
```

Fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NEWSAPI_API_KEY` from your existing crypto-intel-hub (`C:\Users\Koray\.claude\plugins\crypto-intel-hub\data\secrets.env`). Leave `LUNARCRUSH_API_KEY` empty for now (will be acquired in Week 3 Task 3.8).

- [ ] **Step 7: Commit (only the example, NOT secrets.env)**

```powershell
git add src/crypto_predictor/config.py tests/test_config.py data/secrets.env.example
git commit -m "feat(config): secrets loader + template (intel-hub pattern)"
git push
```

Verify `data/secrets.env` is gitignored:
```powershell
git status
```
Expected: no `secrets.env` shown (only `secrets.env.example`).

---

## Task 1.10: Plugin registration with Claude Code

**Files:** none new (registry action)

- [ ] **Step 1: Open Claude Code marketplace add command**

In Claude Code chat:
```
/plugin marketplace add C:\Users\Koray\Desktop\crypto-predictor
```

- [ ] **Step 2: Install the plugin from local marketplace**

In Claude Code chat:
```
/plugin install crypto-predictor@crypto-predictor
```

- [ ] **Step 3: Restart Claude Code session**

Close and reopen Claude Code. This forces MCP servers to be discovered.

- [ ] **Step 4: Verify plugin appears**

In Claude Code chat:
```
/plugin list
```

Expected: `crypto-predictor` appears in the list.

- [ ] **Step 5: Verify MCP tool reachable**

In Claude Code chat, ask:
> "Call the crypto-predictor ping tool."

Expected: response includes `status: ok, version: 0.1.0, timestamp: ...`

- [ ] **Step 6: Commit a Week 1 README**

Create:

```markdown
# crypto-predictor

Heuristic-first probabilistic prediction platform for OKX-Global USDT perpetuals.

**Status**: Phase 1 in progress (Week 1 of 10 complete).
**Design**: [docs/design/2026-06-01-crypto-predictor-design.md](docs/design/2026-06-01-crypto-predictor-design.md)
**Plan A (Weeks 1–3)**: [docs/plans/2026-06-02-phase1-plan-a-foundation.md](docs/plans/2026-06-02-phase1-plan-a-foundation.md)

## Quick start (development)

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
uv venv
uv pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -v
```

## License

MIT
```

Save as `C:\Users\Koray\Desktop\crypto-predictor\README.md`.

```powershell
git add README.md
git commit -m "docs: add Week 1 README pointing at design + plan"
git push
```

**Week 1 done. Verify:**
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
Expected: ~10 tests pass.

---

# Week 2 — Bulk Historical Ingest

Goal: 6 months of historical OHLCV + futures data for 340 perps in Parquet, ready for backtest & feature computation.

## Task 2.1: OKX OHLCV fetcher

**Files:**
- Create: `src/crypto_predictor/data/__init__.py`
- Create: `src/crypto_predictor/data/okx_client.py`
- Create: `tests/data/__init__.py`
- Create: `tests/data/test_okx_client.py`

- [ ] **Step 1: Write the failing test (uses ccxt mock)**

```python
# tests/data/test_okx_client.py
from unittest.mock import MagicMock

import pandas as pd
import pytest

from crypto_predictor.data.okx_client import fetch_ohlcv_paged


def test_fetch_ohlcv_paged_returns_dataframe():
    fake_ccxt = MagicMock()
    # Each fetch_ohlcv returns 3 bars then empty (end of history)
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100.0, 105.0, 99.0, 104.0, 1000.0],
         [1717290000000, 104.0, 106.0, 103.0, 105.0, 1100.0],
         [1717293600000, 105.0, 107.0, 104.0, 106.0, 1200.0]],
        [],
    ]
    df = fetch_ohlcv_paged(fake_ccxt, "BTC-USDT-SWAP", "1h",
                           since_ms=1717286400000, limit_per_page=3)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df.iloc[0]["close"] == 104.0


def test_fetch_ohlcv_paged_handles_empty_first_response():
    fake_ccxt = MagicMock()
    fake_ccxt.fetch_ohlcv.return_value = []
    df = fetch_ohlcv_paged(fake_ccxt, "BTC-USDT-SWAP", "1h",
                           since_ms=1717286400000)
    assert df.empty
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement paged OHLCV fetcher**

```python
# src/crypto_predictor/data/__init__.py
"""Data layer — OKX API client + parquet store."""
```

```python
# src/crypto_predictor/data/okx_client.py
"""Thin ccxt wrapper for OKX with paging + retry."""
from __future__ import annotations

import time

import pandas as pd
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


@retry(stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=1, min=1, max=30))
def _fetch_with_retry(client, symbol: str, timeframe: str,
                      since: int, limit: int) -> list:
    return client.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)


def fetch_ohlcv_paged(
    client,
    symbol: str,
    timeframe: str,
    since_ms: int,
    *,
    limit_per_page: int = 300,
    max_pages: int = 100,
    sleep_between_ms: int = 250,
) -> pd.DataFrame:
    """Fetch OHLCV bars from `since_ms` onward, paging until exhausted.

    Returns a DataFrame with columns [timestamp, open, high, low, close, volume].
    timestamp is integer epoch-ms; conversion to datetime is downstream concern.
    """
    rows: list[list] = []
    cursor = since_ms
    for _ in range(max_pages):
        batch = _fetch_with_retry(client, symbol, timeframe, cursor, limit_per_page)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if len(batch) < limit_per_page:
            break
        cursor = last_ts + 1
        time.sleep(sleep_between_ms / 1000.0)
    if not rows:
        return pd.DataFrame(columns=OHLCV_COLUMNS)
    df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df
```

- [ ] **Step 4: Run test, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_okx_client.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/data/ tests/data/
git commit -m "feat(data): paged OHLCV fetcher with retry + dedup"
git push
```

---

## Task 2.2: Futures data fetcher (funding, OI, L/S ratio, liquidations)

**Files:**
- Modify: `src/crypto_predictor/data/okx_client.py` (add 4 fetcher functions)
- Modify: `tests/data/test_okx_client.py` (add 4 tests)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/data/test_okx_client.py
from crypto_predictor.data.okx_client import (
    fetch_funding_history, fetch_oi_history,
    fetch_long_short_ratio, fetch_liquidations,
)


def test_fetch_funding_history_returns_dataframe():
    fake = MagicMock()
    fake.fetch_funding_rate_history.return_value = [
        {"timestamp": 1717286400000, "fundingRate": 0.0001},
        {"timestamp": 1717312800000, "fundingRate": -0.0002},
    ]
    df = fetch_funding_history(fake, "BTC-USDT-SWAP",
                               since_ms=1717286400000, limit=100)
    assert list(df.columns) == ["timestamp", "funding_rate"]
    assert len(df) == 2
    assert df.iloc[0]["funding_rate"] == 0.0001


def test_fetch_oi_history_returns_dataframe():
    fake = MagicMock()
    fake.fetch_open_interest_history.return_value = [
        {"timestamp": 1717286400000, "openInterestAmount": 12345.0},
        {"timestamp": 1717290000000, "openInterestAmount": 12500.0},
    ]
    df = fetch_oi_history(fake, "BTC-USDT-SWAP",
                          since_ms=1717286400000)
    assert list(df.columns) == ["timestamp", "open_interest"]
    assert len(df) == 2


def test_fetch_long_short_ratio_via_public_api(monkeypatch):
    fake_http = MagicMock()
    fake_http.get.return_value.json.return_value = {
        "data": [
            {"ts": "1717286400000", "longShortRatio": "1.23"},
            {"ts": "1717290000000", "longShortRatio": "1.45"},
        ]
    }
    fake_http.get.return_value.status_code = 200
    df = fetch_long_short_ratio(fake_http, "BTC-USDT-SWAP",
                                period="5m", limit=100)
    assert list(df.columns) == ["timestamp", "ls_ratio"]
    assert len(df) == 2
    assert df.iloc[0]["ls_ratio"] == 1.23


def test_fetch_liquidations_returns_dataframe():
    fake_http = MagicMock()
    fake_http.get.return_value.json.return_value = {
        "data": [{
            "details": [
                {"ts": "1717286400000", "side": "buy", "sz": "1.5", "bkPx": "100"},
                {"ts": "1717286500000", "side": "sell", "sz": "0.5", "bkPx": "101"},
            ]
        }]
    }
    fake_http.get.return_value.status_code = 200
    df = fetch_liquidations(fake_http, "BTC-USDT-SWAP",
                            since_ms=1717286400000)
    assert {"timestamp", "side", "size_usdt"}.issubset(df.columns)
    assert len(df) == 2
```

- [ ] **Step 2: Run tests, verify FAIL**

Expected: ImportError for the four new functions.

- [ ] **Step 3: Add fetchers to okx_client.py**

```python
# append to src/crypto_predictor/data/okx_client.py

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_funding_history(client, symbol: str, since_ms: int,
                          limit: int = 100) -> pd.DataFrame:
    """Fetch funding rate history for a perp via ccxt."""
    rows = client.fetch_funding_rate_history(symbol, since=since_ms, limit=limit)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "funding_rate"])
    df = pd.DataFrame([
        {"timestamp": r["timestamp"], "funding_rate": r["fundingRate"]}
        for r in rows
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_oi_history(client, symbol: str, since_ms: int,
                     limit: int = 100) -> pd.DataFrame:
    """Fetch open interest history for a perp via ccxt."""
    rows = client.fetch_open_interest_history(symbol, since=since_ms, limit=limit)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open_interest"])
    df = pd.DataFrame([
        {"timestamp": r["timestamp"], "open_interest": r["openInterestAmount"]}
        for r in rows
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_long_short_ratio(http_client, symbol: str, *,
                           period: str = "5m", limit: int = 100) -> pd.DataFrame:
    """Fetch L/S account ratio from OKX public API.

    http_client must be an httpx.Client-like object with .get returning a Response
    whose .json() yields {"data": [{"ts": str, "longShortRatio": str}, ...]}.
    """
    url = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
    params = {"ccy": symbol.split("-")[0], "period": period, "limit": limit}
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("ls_ratio_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    data = resp.json().get("data", [])
    if not data:
        return pd.DataFrame(columns=["timestamp", "ls_ratio"])
    df = pd.DataFrame([
        {"timestamp": int(r["ts"]), "ls_ratio": float(r["longShortRatio"])}
        for r in data
    ])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def fetch_liquidations(http_client, symbol: str, since_ms: int) -> pd.DataFrame:
    """Fetch liquidation events from OKX public API."""
    url = "https://www.okx.com/api/v5/public/liquidation-orders"
    params = {"instType": "SWAP", "instId": symbol, "before": str(since_ms)}
    resp = http_client.get(url, params=params)
    if resp.status_code != 200:
        log.warning("liquidations_fetch_failed", symbol=symbol, status=resp.status_code)
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    blocks = resp.json().get("data", [])
    rows = []
    for blk in blocks:
        for d in blk.get("details", []):
            size_usdt = float(d["sz"]) * float(d["bkPx"])
            rows.append({
                "timestamp": int(d["ts"]),
                "side": d["side"],
                "size_usdt": size_usdt,
            })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_okx_client.py -v
```

Expected: 6 tests pass (2 from Task 2.1 + 4 new).

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/data/okx_client.py tests/data/test_okx_client.py
git commit -m "feat(data): funding/OI/L-S/liquidation fetchers via ccxt + OKX public API"
git push
```

---

## Task 2.3: Parquet writer with partitioning

**Files:**
- Create: `src/crypto_predictor/data/parquet_store.py`
- Create: `tests/data/test_parquet_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_parquet_store.py
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import (
    parquet_path, write_ohlcv, read_ohlcv, append_ohlcv,
)


def test_parquet_path_partitioned_by_symbol_and_timeframe(tmp_path: Path):
    p = parquet_path(tmp_path, "BTC-USDT-SWAP", "1h", "ohlcv")
    assert p == tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet"


def test_write_read_roundtrip(tmp_path: Path):
    df = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},
        {"timestamp": 2, "open": 101.0, "high": 103.0, "low": 100.0,
         "close": 102.0, "volume": 1100.0},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    out = read_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h")
    assert len(out) == 2
    assert out.iloc[0]["close"] == 101.0


def test_append_dedups_on_timestamp(tmp_path: Path):
    df1 = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},
    ])
    df2 = pd.DataFrame([
        {"timestamp": 1, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 1000.0},   # dup
        {"timestamp": 2, "open": 101.0, "high": 103.0, "low": 100.0,
         "close": 102.0, "volume": 1100.0},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df1)
    append_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df2)
    out = read_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h")
    assert len(out) == 2
    assert list(out["timestamp"]) == [1, 2]


def test_read_missing_returns_empty(tmp_path: Path):
    out = read_ohlcv(tmp_path, "NOPE", "1h")
    assert out.empty
```

- [ ] **Step 2: Run tests, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement parquet store**

```python
# src/crypto_predictor/data/parquet_store.py
"""Parquet-backed historical store, partitioned by data_kind/symbol/timeframe."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def parquet_path(root: Path, symbol: str, timeframe: str,
                 data_kind: str = "ohlcv") -> Path:
    """Return the canonical parquet path for (data_kind, symbol, timeframe)."""
    return root / data_kind / symbol / f"{timeframe}.parquet"


def write_ohlcv(root: Path, symbol: str, timeframe: str,
                df: pd.DataFrame) -> None:
    """Overwrite the OHLCV parquet for (symbol, timeframe)."""
    path = parquet_path(root, symbol, timeframe, "ohlcv")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def append_ohlcv(root: Path, symbol: str, timeframe: str,
                 df: pd.DataFrame) -> None:
    """Append OHLCV rows, deduplicating on timestamp."""
    existing = read_ohlcv(root, symbol, timeframe)
    if existing.empty:
        write_ohlcv(root, symbol, timeframe, df)
        return
    combined = (
        pd.concat([existing, df], ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    write_ohlcv(root, symbol, timeframe, combined)


def read_ohlcv(root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    """Read OHLCV parquet; return empty frame with canonical columns if missing."""
    path = parquet_path(root, symbol, timeframe, "ohlcv")
    if not path.exists():
        return pd.DataFrame(columns=[
            "timestamp", "open", "high", "low", "close", "volume"
        ])
    return pd.read_parquet(path)
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_parquet_store.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/data/parquet_store.py tests/data/test_parquet_store.py
git commit -m "feat(data): parquet store with partition layout + dedup append"
git push
```

---

## Task 2.4: Resume / idempotency logic for ingest

**Files:**
- Create: `src/crypto_predictor/data/ingest_state.py`
- Create: `tests/data/test_ingest_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_ingest_state.py
from pathlib import Path

import pandas as pd

from crypto_predictor.data.ingest_state import next_since_ms_for_ohlcv


def test_returns_default_when_no_existing_parquet(tmp_path: Path):
    default = 1700000000000
    since = next_since_ms_for_ohlcv(tmp_path, "ABCUSDT", "1h", default_since_ms=default)
    assert since == default


def test_returns_last_timestamp_plus_one_when_parquet_exists(tmp_path: Path):
    from crypto_predictor.data.parquet_store import write_ohlcv
    df = pd.DataFrame([
        {"timestamp": 1717286400000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
        {"timestamp": 1717290000000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
    ])
    write_ohlcv(tmp_path, "ABCUSDT", "1h", df)
    since = next_since_ms_for_ohlcv(tmp_path, "ABCUSDT", "1h", default_since_ms=0)
    assert since == 1717290000000 + 1
```

- [ ] **Step 2: Run tests, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement resume logic**

```python
# src/crypto_predictor/data/ingest_state.py
"""Compute the next `since` cursor for resumable ingest."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.data.parquet_store import read_ohlcv


def next_since_ms_for_ohlcv(root: Path, symbol: str, timeframe: str,
                            *, default_since_ms: int) -> int:
    """Return the timestamp from which ingest should resume.

    If parquet exists, return last_timestamp + 1. Otherwise return default.
    """
    existing = read_ohlcv(root, symbol, timeframe)
    if existing.empty:
        return default_since_ms
    return int(existing["timestamp"].max()) + 1
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_ingest_state.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/data/ingest_state.py tests/data/test_ingest_state.py
git commit -m "feat(data): resumable ingest cursor based on existing parquet"
git push
```

---

## Task 2.5: Bulk-ingest orchestrator script

**Files:**
- Create: `scripts/ingest_history.py`
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/test_ingest_history_smoke.py`

- [ ] **Step 1: Write the failing test (synthetic, no live API)**

```python
# tests/scripts/test_ingest_history_smoke.py
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from scripts.ingest_history import ingest_symbol_ohlcv


def test_ingest_symbol_ohlcv_writes_parquet(tmp_path: Path):
    fake_ccxt = MagicMock()
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100, 101, 99, 100, 500],
         [1717290000000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt,
        root=tmp_path,
        symbol="BTC-USDT-SWAP",
        timeframe="1h",
        since_ms=1717286400000,
    )
    out = pd.read_parquet(tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet")
    assert len(out) == 2


def test_ingest_symbol_ohlcv_is_resumable(tmp_path: Path):
    fake_ccxt = MagicMock()
    # First run
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717286400000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt, root=tmp_path, symbol="BTC-USDT-SWAP",
        timeframe="1h", since_ms=1717286400000,
    )
    # Second run with new data
    fake_ccxt.fetch_ohlcv.side_effect = [
        [[1717290000000, 100, 101, 99, 100, 500]],
        [],
    ]
    ingest_symbol_ohlcv(
        client=fake_ccxt, root=tmp_path, symbol="BTC-USDT-SWAP",
        timeframe="1h", since_ms=1717286400000,
    )
    out = pd.read_parquet(tmp_path / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet")
    assert len(out) == 2  # both rows present, no dup
```

- [ ] **Step 2: Run tests, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement orchestrator script**

```python
# scripts/__init__.py  (create empty if missing)
```

```python
# scripts/ingest_history.py
"""Bulk-ingest 6 months of OKX-Global perp data into parquet.

Run once at project setup. Idempotent + resumable. Wall-clock ~6 hours
due to OKX rate limits.

Usage:
    python scripts/ingest_history.py --root data/history --months 6
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import httpx
import structlog

from crypto_predictor.data.ingest_state import next_since_ms_for_ohlcv
from crypto_predictor.data.okx_client import (
    fetch_funding_history, fetch_liquidations, fetch_long_short_ratio,
    fetch_ohlcv_paged, fetch_oi_history,
)
from crypto_predictor.data.parquet_store import (
    append_ohlcv, parquet_path, write_ohlcv,
)
from crypto_predictor.logging_config import configure_logging

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

log = structlog.get_logger(__name__)


def ingest_symbol_ohlcv(client, root: Path, symbol: str, timeframe: str,
                        since_ms: int) -> int:
    """Ingest OHLCV for one (symbol, timeframe). Returns row count written."""
    cursor = next_since_ms_for_ohlcv(root, symbol, timeframe,
                                     default_since_ms=since_ms)
    df = fetch_ohlcv_paged(client, symbol, timeframe, cursor)
    if df.empty:
        return 0
    append_ohlcv(root, symbol, timeframe, df)
    return len(df)


def ingest_symbol_futures(ccxt_client, http_client, root: Path,
                          symbol: str, since_ms: int) -> dict[str, int]:
    """Ingest funding + OI + L/S + liquidations for one symbol."""
    counts = {}

    # Funding
    fpath = parquet_path(root, symbol, "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    f_df = fetch_funding_history(ccxt_client, symbol, since_ms)
    if not f_df.empty:
        f_df.to_parquet(fpath, index=False)
    counts["funding"] = len(f_df)

    # OI
    oi_df = fetch_oi_history(ccxt_client, symbol, since_ms)
    oipath = parquet_path(root, symbol, "oi", "futures")
    oipath.parent.mkdir(parents=True, exist_ok=True)
    if not oi_df.empty:
        oi_df.to_parquet(oipath, index=False)
    counts["oi"] = len(oi_df)

    # L/S ratio
    ls_df = fetch_long_short_ratio(http_client, symbol, period="5m", limit=500)
    lspath = parquet_path(root, symbol, "ls_ratio", "futures")
    lspath.parent.mkdir(parents=True, exist_ok=True)
    if not ls_df.empty:
        ls_df.to_parquet(lspath, index=False)
    counts["ls_ratio"] = len(ls_df)

    # Liquidations
    liq_df = fetch_liquidations(http_client, symbol, since_ms)
    liqpath = parquet_path(root, symbol, "liq", "futures")
    liqpath.parent.mkdir(parents=True, exist_ok=True)
    if not liq_df.empty:
        liq_df.to_parquet(liqpath, index=False)
    counts["liq"] = len(liq_df)

    return counts


def list_okx_perps(client) -> list[str]:
    """Return list of active USDT-margined perpetual symbols on OKX."""
    markets = client.load_markets()
    return [
        m["symbol"] for m in markets.values()
        if m.get("swap") and m.get("settle") == "USDT" and m.get("active")
    ]


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True,
                        help="Output root, e.g. data/history")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--limit-symbols", type=int, default=None,
                        help="For testing: ingest only first N symbols")
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)

    okx = ccxt.okx({"enableRateLimit": True})
    http = httpx.Client(timeout=30.0)

    since_dt = datetime.now(timezone.utc).timestamp() * 1000 - args.months * 30 * 86400 * 1000
    since_ms = int(since_dt)

    symbols = list_okx_perps(okx)
    if args.limit_symbols:
        symbols = symbols[:args.limit_symbols]
    log.info("ingest_start", n_symbols=len(symbols), months=args.months)

    for i, sym in enumerate(symbols, start=1):
        try:
            for tf in TIMEFRAMES:
                n = ingest_symbol_ohlcv(okx, args.root, sym, tf, since_ms)
                log.info("ohlcv_done", symbol=sym, timeframe=tf, rows=n,
                         progress=f"{i}/{len(symbols)}")
            counts = ingest_symbol_futures(okx, http, args.root, sym, since_ms)
            log.info("futures_done", symbol=sym, **counts)
        except Exception as exc:  # pragma: no cover
            log.error("symbol_failed", symbol=sym, error=str(exc))
        time.sleep(0.25)

    log.info("ingest_complete", n_symbols=len(symbols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run unit tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/scripts/test_ingest_history_smoke.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/ingest_history.py tests/scripts/
git commit -m "feat(scripts): bulk ingest orchestrator with resume + futures data"
git push
```

---

## Task 2.6: Smoke test on 5-coin / 30-day slice

**Files:** none new (live execution)

- [ ] **Step 1: Run small ingest**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe scripts\ingest_history.py --root data\history --months 1 --limit-symbols 5
```

Expected: log lines for 5 symbols × 4 timeframes + 4 futures kinds. Should complete in ~5–10 minutes.

- [ ] **Step 2: Verify parquet structure**

```powershell
Get-ChildItem -Path data\history -Recurse -Filter *.parquet | Select-Object FullName, Length | Format-Table -AutoSize
```

Expected: each of 5 symbols has 4 ohlcv parquets + funding/oi/ls_ratio/liq under their `futures/` partition.

- [ ] **Step 3: Spot-check one parquet**

```powershell
.\.venv\Scripts\python.exe -c "import pandas as pd; df = pd.read_parquet('data/history/ohlcv/BTC-USDT-SWAP/1h.parquet'); print(df.head()); print('rows:', len(df))"
```

Expected: a head DataFrame, ~700 rows for 1 month of 1h bars.

- [ ] **Step 4: Document smoke test result**

Create `data/history/.smoke_test_passed`:

```
Smoke test completed: 2026-06-??
Symbols ingested: BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP, BNB-USDT-SWAP, XRP-USDT-SWAP (or whatever first-5 alphabetical gave)
Timeframes: 15m, 1h, 4h, 1d
Futures: funding, oi, ls_ratio, liq
Notes: <any anomalies observed>
```

- [ ] **Step 5: No commit (data/history/ is gitignored)**

---

## Task 2.7: Run full ingest (long-running manual step)

**Files:** none new (live execution, ~6 hours)

- [ ] **Step 1: Schedule the run**

Pick a time when laptop will be awake for ~6 hours uninterrupted (overnight + caffeinate). Use a separate PowerShell window so other Claude sessions can continue.

- [ ] **Step 2: Disable laptop sleep during run**

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
```

(Restore with `powercfg /change standby-timeout-ac 30` etc. after run.)

- [ ] **Step 3: Start the ingest**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe scripts\ingest_history.py --root data\history --months 6 *> ingest.log
```

(The `*>` redirects all streams to a log file so you can review afterwards.)

- [ ] **Step 4: Periodically check progress**

In another shell:
```powershell
Get-Content C:\Users\Koray\Desktop\crypto-predictor\ingest.log -Tail 20
```

Look for `progress: N/340` lines. If a symbol fails, the script logs and continues.

- [ ] **Step 5: Verify completion**

When the script returns, check:
```powershell
Select-String -Path ingest.log -Pattern "ingest_complete"
```

Expected: one match.

- [ ] **Step 6: Stats summary**

```powershell
.\.venv\Scripts\python.exe -c "
from pathlib import Path
import pandas as pd
root = Path('data/history/ohlcv')
syms = list(root.iterdir())
print('symbols:', len(syms))
total_rows = sum(len(pd.read_parquet(p)) for s in syms for p in s.glob('*.parquet'))
print('total ohlcv rows:', total_rows)
"
```

Expected: ~330–340 symbols (some delisted between universe fetch and ingest end), ~6M rows total.

- [ ] **Step 7: No commit (data/history/ is gitignored). Save log if interesting.**

---

## Task 2.8: Ingest verification query

**Files:**
- Create: `scripts/verify_ingest.py`

- [ ] **Step 1: Write verification script**

```python
# scripts/verify_ingest.py
"""Sanity-check the ingested parquet store: counts, coverage, freshness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/history"))
    args = parser.parse_args()

    ohlcv_root = args.root / "ohlcv"
    futures_root = args.root / "futures"
    if not ohlcv_root.exists():
        print(f"ERROR: {ohlcv_root} does not exist. Run ingest_history first.")
        return 1

    symbols = sorted(p.name for p in ohlcv_root.iterdir() if p.is_dir())
    print(f"Symbols ingested: {len(symbols)}")

    timeframes = ["15m", "1h", "4h", "1d"]
    rows_per_tf: dict[str, int] = {tf: 0 for tf in timeframes}
    missing_tf: list[tuple[str, str]] = []
    stale_count = 0
    stale_cutoff = (datetime.now(timezone.utc).timestamp() - 86400) * 1000

    for sym in symbols:
        for tf in timeframes:
            p = ohlcv_root / sym / f"{tf}.parquet"
            if not p.exists():
                missing_tf.append((sym, tf))
                continue
            df = pd.read_parquet(p)
            rows_per_tf[tf] += len(df)
            if not df.empty and df["timestamp"].max() < stale_cutoff:
                stale_count += 1

    print(f"\nOHLCV rows by timeframe:")
    for tf, n in rows_per_tf.items():
        print(f"  {tf}: {n:,}")
    print(f"\nMissing (symbol, timeframe) pairs: {len(missing_tf)}")
    if missing_tf[:5]:
        print(f"  examples: {missing_tf[:5]}")
    print(f"\nSymbol/timeframe pairs with stale last bar (>24h old): {stale_count}")

    # Futures coverage
    futures_symbols = sorted(p.name for p in futures_root.iterdir() if p.is_dir())
    print(f"\nFutures-data symbols: {len(futures_symbols)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run verification**

```powershell
.\.venv\Scripts\python.exe scripts\verify_ingest.py --root data\history
```

Expected output:
```
Symbols ingested: ~340
OHLCV rows by timeframe:
  15m: ~5,800,000
  1h:  ~1,460,000
  4h:    ~365,000
  1d:     ~61,000
Missing pairs: 0–50 (some delisted mid-ingest is normal)
Stale: 0–50
Futures-data symbols: ~340
```

- [ ] **Step 3: Commit verification script**

```powershell
git add scripts/verify_ingest.py
git commit -m "feat(scripts): ingest verification (counts + coverage + freshness)"
git push
```

**Week 2 done. Verify:**
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
Expected: ~18 tests pass (10 from Week 1 + ~8 from Week 2).

---

# Week 3 — Feature Pipeline

Goal: compute ~30 z-scored features per coin, plug-and-play for backtest (Week 5) and live (Week 7). Strict look-ahead-bias guard.

## Task 3.1: FeatureFetcher with asof guard

**Files:**
- Create: `src/crypto_predictor/features/__init__.py`
- Create: `src/crypto_predictor/features/fetcher.py`
- Create: `tests/features/__init__.py`
- Create: `tests/features/test_fetcher_asof_guard.py`

- [ ] **Step 1: Write the failing test — this is the look-ahead-bias-guard test**

```python
# tests/features/test_fetcher_asof_guard.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher


@pytest.fixture
def history_with_bars(tmp_path: Path) -> Path:
    df = pd.DataFrame([
        {"timestamp": 1717286400000, "open": 100, "high": 101, "low": 99,
         "close": 100, "volume": 500},
        {"timestamp": 1717290000000, "open": 100, "high": 101, "low": 99,
         "close": 101, "volume": 500},
        {"timestamp": 1717293600000, "open": 101, "high": 102, "low": 100,
         "close": 102, "volume": 500},
    ])
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    return tmp_path


def test_fetcher_returns_bars_strictly_before_asof(history_with_bars: Path):
    # asof = second bar timestamp; only the first bar must be returned
    asof = datetime.fromtimestamp(1717290000000 / 1000, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=10)
    assert len(df) == 1
    assert df.iloc[0]["timestamp"] == 1717286400000


def test_fetcher_respects_lookback(history_with_bars: Path):
    asof = datetime.fromtimestamp(1717293600000 / 1000 + 1, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=2)
    assert len(df) == 2
    # The two MOST RECENT bars before asof
    assert df.iloc[-1]["close"] == 102


def test_fetcher_raises_on_future_query(history_with_bars: Path):
    asof = datetime.fromtimestamp(1717290000000 / 1000, tz=timezone.utc)
    f = FeatureFetcher(root=history_with_bars, asof=asof)
    # Even though caller might do something silly, the public API
    # must guard against returning anything >= asof.
    df = f.ohlcv("BTC-USDT-SWAP", "1h", lookback_bars=100)
    assert (df["timestamp"] < int(asof.timestamp() * 1000)).all()
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement FeatureFetcher**

```python
# src/crypto_predictor/features/__init__.py
"""Feature pipeline — vectorized computation with strict asof guard."""
```

```python
# src/crypto_predictor/features/fetcher.py
"""asof-guarded data fetcher used by every feature computation.

CRITICAL: every read MUST go through this class so look-ahead bias is
impossible in backtest. Tests in tests/features/test_fetcher_asof_guard.py
enforce this invariant.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path


@dataclass(frozen=True)
class FeatureFetcher:
    """Fetcher pinned to a specific point in time. All reads filter timestamps < asof."""

    root: Path
    asof: datetime

    @property
    def _asof_ms(self) -> int:
        return int(self.asof.timestamp() * 1000)

    def ohlcv(self, symbol: str, timeframe: str,
              lookback_bars: int) -> pd.DataFrame:
        """Return the last `lookback_bars` OHLCV rows strictly before asof."""
        path = parquet_path(self.root, symbol, timeframe, "ohlcv")
        if not path.exists():
            return pd.DataFrame(columns=[
                "timestamp", "open", "high", "low", "close", "volume"
            ])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_bars).reset_index(drop=True)

    def funding(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "funding", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "funding_rate"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def open_interest(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "oi", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "open_interest"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def ls_ratio(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "ls_ratio", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "ls_ratio"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def liquidations(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "liq", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/test_fetcher_asof_guard.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/ tests/features/
git commit -m "feat(features): FeatureFetcher with strict asof guard (look-ahead-bias prevention)"
git push
```

---

## Task 3.2: Z-score normalizer

**Files:**
- Create: `src/crypto_predictor/features/normalize.py`
- Create: `tests/features/test_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_normalize.py
import numpy as np

from crypto_predictor.features.normalize import zscore, robust_zscore


def test_zscore_normal_case():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z = zscore(arr, arr)
    # The most recent value (5.0) — mean=3, std=√2 → z ≈ 1.41
    assert abs(z - 1.4142) < 0.001


def test_zscore_zero_std_returns_zero():
    arr = np.array([3.0, 3.0, 3.0])
    z = zscore(3.0, arr)
    assert z == 0.0


def test_zscore_nan_population_returns_zero():
    arr = np.array([np.nan, np.nan, np.nan])
    z = zscore(1.0, arr)
    assert z == 0.0


def test_robust_zscore_uses_median_and_mad():
    arr = np.array([1.0, 2.0, 3.0, 100.0])  # 100 is outlier
    z = robust_zscore(1.0, arr)
    # robust to outliers; classical z would be heavily skewed
    assert abs(z) < 10  # sanity bound; exact depends on MAD
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement normalize module**

```python
# src/crypto_predictor/features/normalize.py
"""Feature normalization — z-score and robust z-score."""
from __future__ import annotations

import numpy as np


def zscore(value: float, population: np.ndarray) -> float:
    """Standard z-score of `value` against `population`.

    Returns 0.0 if population is empty, all-NaN, or zero-variance.
    """
    p = np.asarray(population, dtype=float)
    p = p[~np.isnan(p)]
    if p.size == 0:
        return 0.0
    mean = p.mean()
    std = p.std(ddof=0)
    if std == 0 or np.isnan(std):
        return 0.0
    return float((value - mean) / std)


def robust_zscore(value: float, population: np.ndarray) -> float:
    """Robust z-score using median + median-absolute-deviation."""
    p = np.asarray(population, dtype=float)
    p = p[~np.isnan(p)]
    if p.size == 0:
        return 0.0
    median = np.median(p)
    mad = np.median(np.abs(p - median))
    if mad == 0:
        return 0.0
    return float((value - median) / (1.4826 * mad))  # 1.4826 = MAD→sigma constant
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/test_normalize.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/normalize.py tests/features/test_normalize.py
git commit -m "feat(features): z-score + robust z-score normalizers with edge-case handling"
git push
```

---

## Task 3.3: Momentum feature family

**Files:**
- Create: `src/crypto_predictor/features/families/__init__.py`
- Create: `src/crypto_predictor/features/families/momentum.py`
- Create: `tests/features/families/__init__.py`
- Create: `tests/features/families/test_momentum.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_momentum.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.momentum import compute_momentum_features
from crypto_predictor.features.fetcher import FeatureFetcher


def make_synthetic_1h_bars(n: int, start_ms: int, start_price: float = 100.0,
                           drift_per_bar: float = 0.001) -> pd.DataFrame:
    rows = []
    p = start_price
    for i in range(n):
        rows.append({
            "timestamp": start_ms + i * 3600 * 1000,
            "open": p,
            "high": p * 1.005,
            "low": p * 0.995,
            "close": p * (1 + drift_per_bar),
            "volume": 1000,
        })
        p = p * (1 + drift_per_bar)
    return pd.DataFrame(rows)


def test_momentum_features_returns_expected_keys(tmp_path: Path):
    df = make_synthetic_1h_bars(n=2200, start_ms=1700000000000)  # ~3 months
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    # Also need 15m and 1d (Family uses 15m and daily). Reuse 1h reshape for test.
    df_15m = make_synthetic_1h_bars(n=8800, start_ms=1700000000000,
                                    drift_per_bar=0.00025)
    df_15m["timestamp"] = 1700000000000 + (df_15m.index * 900 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "15m", df_15m)
    df_4h = make_synthetic_1h_bars(n=550, start_ms=1700000000000,
                                   drift_per_bar=0.004)
    df_4h["timestamp"] = 1700000000000 + (df_4h.index * 14400 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "4h", df_4h)
    df_1d = make_synthetic_1h_bars(n=100, start_ms=1700000000000,
                                   drift_per_bar=0.024)
    df_1d["timestamp"] = 1700000000000 + (df_1d.index * 86400 * 1000)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1d", df_1d)

    asof = datetime.fromtimestamp((1700000000000 + 90 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_momentum_features(fetcher, "BTC-USDT-SWAP")
    expected = {"ret_15m_z", "ret_1h_z", "ret_4h_z", "ret_24h_z",
                "ret_7d_z", "mom_consistency"}
    assert expected.issubset(set(feats.keys()))


def test_momentum_consistency_in_unit_range(tmp_path: Path):
    df = make_synthetic_1h_bars(n=2200, start_ms=1700000000000,
                                drift_per_bar=0.001)
    write_ohlcv(tmp_path, "BTC-USDT-SWAP", "1h", df)
    asof = datetime.fromtimestamp((1700000000000 + 90 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_momentum_features(fetcher, "BTC-USDT-SWAP")
    assert 0.0 <= feats["mom_consistency"] <= 1.0
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement momentum family**

```python
# src/crypto_predictor/features/families/__init__.py
"""Six feature families."""
```

```python
# src/crypto_predictor/features/families/momentum.py
"""Family 1 — momentum: multi-timeframe log returns, z-scored, plus consistency."""
from __future__ import annotations

import math

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def _log_return(df, periods: int) -> float | None:
    if df.empty or len(df) <= periods:
        return None
    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-1 - periods]
    if prev <= 0:
        return None
    return math.log(last / prev)


def _historical_returns(df, periods: int, max_samples: int = 1000) -> np.ndarray:
    closes = df["close"].values
    if len(closes) <= periods:
        return np.array([])
    rets = np.log(closes[periods:] / closes[:-periods])
    return rets[-max_samples:]


def compute_momentum_features(fetcher: FeatureFetcher,
                              symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}

    # 15m return → z-score against 90d 15m bars (90×96 = 8640)
    df15 = fetcher.ohlcv(symbol, "15m", lookback_bars=8640)
    r = _log_return(df15, 1)
    pop = _historical_returns(df15, 1)
    feats["ret_15m_z"] = zscore(r, pop) if r is not None else 0.0

    # 1h return → z-score against 90d 1h bars (2160)
    df1h = fetcher.ohlcv(symbol, "1h", lookback_bars=2200)
    r = _log_return(df1h, 1)
    pop = _historical_returns(df1h, 1)
    feats["ret_1h_z"] = zscore(r, pop) if r is not None else 0.0

    # 4h return → z-score against 90d 4h bars (540)
    df4h = fetcher.ohlcv(symbol, "4h", lookback_bars=600)
    r = _log_return(df4h, 1)
    pop = _historical_returns(df4h, 1)
    feats["ret_4h_z"] = zscore(r, pop) if r is not None else 0.0

    # 24h return → z-score against 90d 1d bars
    df1d = fetcher.ohlcv(symbol, "1d", lookback_bars=100)
    r = _log_return(df1d, 1)
    pop = _historical_returns(df1d, 1)
    feats["ret_24h_z"] = zscore(r, pop) if r is not None else 0.0

    # 7d return → z-score against 90d 1d bars, lag=7
    r = _log_return(df1d, 7)
    pop = _historical_returns(df1d, 7)
    feats["ret_7d_z"] = zscore(r, pop) if r is not None else 0.0

    # Momentum consistency: fraction of last 24×1h bars that went up
    if df1h.empty or len(df1h) < 25:
        feats["mom_consistency"] = 0.5
    else:
        last_25 = df1h.tail(25)
        diffs = last_25["close"].diff().dropna()
        ups = (diffs > 0).sum()
        feats["mom_consistency"] = float(ups) / len(diffs)

    return feats
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_momentum.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/ tests/features/families/
git commit -m "feat(features): family 1 momentum — 6 z-scored returns + consistency"
git push
```

---

## Task 3.4: Perp microstructure feature family

**Files:**
- Create: `src/crypto_predictor/features/families/perp.py`
- Create: `tests/features/families/test_perp.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_perp.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path
from crypto_predictor.features.families.perp import compute_perp_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _write_parquet(root: Path, symbol: str, kind: str, df: pd.DataFrame):
    p = parquet_path(root, symbol, kind, "futures")
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def test_perp_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    # 30d of 8-hour funding samples = 90 rows
    f_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000,
         "funding_rate": 0.0001 * ((-1) ** i)}
        for i in range(90)
    ])
    _write_parquet(tmp_path, sym, "funding", f_df)

    oi_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 3600 * 1000,
         "open_interest": 10000 + i * 10}
        for i in range(720)  # 30d × 24h
    ])
    _write_parquet(tmp_path, sym, "oi", oi_df)

    ls_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 300 * 1000,
         "ls_ratio": 1.0 + 0.01 * ((-1) ** i)}
        for i in range(200)
    ])
    _write_parquet(tmp_path, sym, "ls_ratio", ls_df)

    liq_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 60 * 1000,
         "side": "buy" if i % 2 else "sell",
         "size_usdt": 5000}
        for i in range(50)
    ])
    _write_parquet(tmp_path, sym, "liq", liq_df)

    # OHLCV needed by tilt logic later but compute_perp_features doesn't need it
    from crypto_predictor.data.parquet_store import write_ohlcv
    write_ohlcv(tmp_path, sym, "4h",
                pd.DataFrame([{"timestamp": 1700000000000, "open": 100,
                               "high": 101, "low": 99, "close": 100,
                               "volume": 500}]))

    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_perp_features(fetcher, sym)
    expected = {"funding_z", "funding_extreme", "oi_growth_24h", "oi_growth_z",
                "ls_ratio", "ls_ratio_change_4h", "taker_buy_sell_1h",
                "liq_pressure_long_4h", "liq_pressure_short_4h"}
    assert expected.issubset(set(feats.keys()))


def test_funding_extreme_is_binary(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    # All-zero funding → funding_extreme=0
    f_df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000, "funding_rate": 0.0}
        for i in range(90)
    ])
    _write_parquet(tmp_path, sym, "funding", f_df)
    # ensure other parquets exist as empties
    for k in ["oi", "ls_ratio", "liq"]:
        _write_parquet(tmp_path, sym, k, pd.DataFrame())
    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_perp_features(fetcher, sym)
    assert feats["funding_extreme"] in (0.0, 1.0)
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement perp microstructure family**

```python
# src/crypto_predictor/features/families/perp.py
"""Family 2 — perp microstructure: funding, OI, L/S, liquidations."""
from __future__ import annotations

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def compute_perp_features(fetcher: FeatureFetcher,
                          symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}

    # Funding
    f_df = fetcher.funding(symbol, lookback_rows=100)
    if not f_df.empty:
        latest = float(f_df["funding_rate"].iloc[-1])
        pop = f_df["funding_rate"].values
        feats["funding_z"] = zscore(latest, pop)
        feats["funding_extreme"] = 1.0 if abs(feats["funding_z"]) > 2.0 else 0.0
    else:
        feats["funding_z"] = 0.0
        feats["funding_extreme"] = 0.0

    # Open interest growth
    oi_df = fetcher.open_interest(symbol, lookback_rows=800)
    if len(oi_df) >= 25:
        now_oi = float(oi_df["open_interest"].iloc[-1])
        oi_24h_ago = float(oi_df["open_interest"].iloc[-25])
        growth = (now_oi / oi_24h_ago - 1.0) if oi_24h_ago > 0 else 0.0
        feats["oi_growth_24h"] = growth
        # Population of 24h growth rates over historical window
        closes = oi_df["open_interest"].values
        growths = (closes[24:] / closes[:-24]) - 1.0 if len(closes) > 24 else np.array([])
        feats["oi_growth_z"] = zscore(growth, growths)
    else:
        feats["oi_growth_24h"] = 0.0
        feats["oi_growth_z"] = 0.0

    # Long/short ratio
    ls_df = fetcher.ls_ratio(symbol, lookback_rows=200)
    if not ls_df.empty:
        feats["ls_ratio"] = float(ls_df["ls_ratio"].iloc[-1])
        if len(ls_df) >= 49:  # 4h × 12 samples/hr at 5m
            ls_4h_ago = float(ls_df["ls_ratio"].iloc[-49])
            feats["ls_ratio_change_4h"] = feats["ls_ratio"] - ls_4h_ago
        else:
            feats["ls_ratio_change_4h"] = 0.0
    else:
        feats["ls_ratio"] = 1.0
        feats["ls_ratio_change_4h"] = 0.0

    # Liquidations (last 4h)
    liq_df = fetcher.liquidations(symbol, lookback_rows=2000)
    if not liq_df.empty:
        cutoff_ms = fetcher._asof_ms - 4 * 3600 * 1000
        liq_4h = liq_df[liq_df["timestamp"] >= cutoff_ms]
        feats["liq_pressure_long_4h"] = float(
            liq_4h[liq_4h["side"] == "sell"]["size_usdt"].sum()
        )
        feats["liq_pressure_short_4h"] = float(
            liq_4h[liq_4h["side"] == "buy"]["size_usdt"].sum()
        )
    else:
        feats["liq_pressure_long_4h"] = 0.0
        feats["liq_pressure_short_4h"] = 0.0

    # Taker buy/sell — derived from OHLCV+OI: approximation via OI delta sign × volume.
    # Phase 1 approximation: use 1h candle close vs open as proxy of net taker direction.
    h_df = fetcher.ohlcv(symbol, "1h", lookback_bars=2)
    if len(h_df) >= 1:
        row = h_df.iloc[-1]
        body = float(row["close"] - row["open"])
        total = float(row["high"] - row["low"]) or 1.0
        # 0.5 = neutral, >0.5 = taker buy dominant
        feats["taker_buy_sell_1h"] = max(0.0, min(1.0, 0.5 + (body / total) * 0.5))
    else:
        feats["taker_buy_sell_1h"] = 0.5

    return feats
```

> **Note for engineer**: the `taker_buy_sell` feature here is a Phase-1 approximation (candle-body proxy). True taker buy/sell volume requires the OKX `/trades` endpoint per minute — too expensive for 340 coins daily. v0.2 may upgrade.

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_perp.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/perp.py tests/features/families/test_perp.py
git commit -m "feat(features): family 2 perp microstructure — 9 features"
git push
```

---

## Task 3.5: Volume / liquidity feature family

**Files:**
- Create: `src/crypto_predictor/features/families/volume.py`
- Create: `tests/features/families/test_volume.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_volume.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.volume import compute_volume_features
from crypto_predictor.features.fetcher import FeatureFetcher


def test_volume_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 86400 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100, "volume": 1000 + i}
        for i in range(40)
    ])
    write_ohlcv(tmp_path, sym, "1d", df)
    asof = datetime.fromtimestamp((1700000000000 + 41 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_volume_features(fetcher, sym)
    expected = {"vol_z_24h"}  # spread/depth come from microstructure MCP in Week 7
    assert expected.issubset(set(feats.keys()))


def test_vol_z_24h_positive_when_spike(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    rows = [
        {"timestamp": 1700000000000 + i * 86400 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100, "volume": 1000}
        for i in range(30)
    ]
    # Spike on the last day
    rows.append({"timestamp": 1700000000000 + 30 * 86400 * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 10_000})
    write_ohlcv(tmp_path, sym, "1d", pd.DataFrame(rows))
    asof = datetime.fromtimestamp((1700000000000 + 31 * 86400 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_volume_features(fetcher, sym)
    assert feats["vol_z_24h"] > 3.0
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement volume family**

```python
# src/crypto_predictor/features/families/volume.py
"""Family 3 — volume/liquidity. Phase 1 covers volume_z; spread/depth in Week 7."""
from __future__ import annotations

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def compute_volume_features(fetcher: FeatureFetcher,
                            symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}
    df = fetcher.ohlcv(symbol, "1d", lookback_bars=35)
    if df.empty:
        feats["vol_z_24h"] = 0.0
        return feats
    latest_vol = float(df["volume"].iloc[-1])
    pop = df["volume"].values[:-1]  # exclude the value we're scoring
    feats["vol_z_24h"] = zscore(latest_vol, pop)
    return feats
```

> **Note**: `spread_bps`, `depth_1pct`, `vol_vs_mcap_rank` come from live MCP servers (microstructure + market_data) and are added in Week 7's orchestrator, not Plan A.

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_volume.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/volume.py tests/features/families/test_volume.py
git commit -m "feat(features): family 3 volume — vol_z_24h (spread/depth deferred to Week 7)"
git push
```

---

## Task 3.6: Technical feature family

**Files:**
- Create: `src/crypto_predictor/features/families/technical.py`
- Create: `tests/features/families/test_technical.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_technical.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.families.technical import compute_technical_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _make_bars(n: int, start_ms: int = 1700000000000) -> pd.DataFrame:
    return pd.DataFrame([
        {"timestamp": start_ms + i * 3600 * 1000, "open": 100 + i * 0.1,
         "high": 101 + i * 0.1, "low": 99 + i * 0.1, "close": 100 + i * 0.1,
         "volume": 1000}
        for i in range(n)
    ])


def test_technical_features_returns_expected_keys(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(200))
    asof = datetime.fromtimestamp((1700000000000 + 250 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    expected = {"rsi_14_1h", "rsi_overbought", "rsi_oversold", "macd_hist_1h",
                "bb_position_1h", "price_vs_sma50"}
    assert expected.issubset(set(feats.keys()))


def test_rsi_is_in_range(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(200))
    asof = datetime.fromtimestamp((1700000000000 + 250 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    assert 0 <= feats["rsi_14_1h"] <= 100


def test_bb_position_in_unit_range_for_uptrend(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    write_ohlcv(tmp_path, sym, "1h", _make_bars(100))
    asof = datetime.fromtimestamp((1700000000000 + 150 * 3600 * 1000) / 1000,
                                  tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_technical_features(fetcher, sym)
    # Steady uptrend: price clings to upper band, position close to 1
    assert -0.5 <= feats["bb_position_1h"] <= 1.5
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement technical family**

```python
# src/crypto_predictor/features/families/technical.py
"""Family 4 — technical indicators (RSI, MACD, BB, SMA). ADX in Week 7."""
from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_predictor.features.fetcher import FeatureFetcher


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diff = np.diff(closes)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    if len(arr) == 0:
        return arr
    alpha = 2 / (period + 1)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _macd_hist(closes: np.ndarray) -> float:
    if len(closes) < 35:
        return 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    return float(macd[-1] - signal[-1])


def _bb_position(closes: np.ndarray, period: int = 20, k: float = 2.0) -> float:
    if len(closes) < period:
        return 0.5
    window = closes[-period:]
    mid = window.mean()
    sd = window.std(ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    if upper == lower:
        return 0.5
    return float((closes[-1] - lower) / (upper - lower))


def compute_technical_features(fetcher: FeatureFetcher,
                               symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}
    df = fetcher.ohlcv(symbol, "1h", lookback_bars=200)
    if df.empty:
        return {"rsi_14_1h": 50.0, "rsi_overbought": 0.0, "rsi_oversold": 0.0,
                "macd_hist_1h": 0.0, "bb_position_1h": 0.5,
                "price_vs_sma50": 0.0}
    closes = df["close"].values
    rsi = _rsi(closes, 14)
    feats["rsi_14_1h"] = rsi
    feats["rsi_overbought"] = 1.0 if rsi > 70 else 0.0
    feats["rsi_oversold"] = 1.0 if rsi < 30 else 0.0
    feats["macd_hist_1h"] = _macd_hist(closes)
    feats["bb_position_1h"] = _bb_position(closes)
    sma50 = closes[-50:].mean() if len(closes) >= 50 else closes.mean()
    feats["price_vs_sma50"] = float((closes[-1] / sma50) - 1.0) if sma50 else 0.0
    return feats
```

> **Note**: ADX requires the `crypto-advanced-indicators` MCP (live data) — added in Week 7 orchestrator, not Plan A.

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_technical.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/technical.py tests/features/families/test_technical.py
git commit -m "feat(features): family 4 technical — RSI, MACD, BB, SMA (ADX deferred)"
git push
```

---

## Task 3.7: Sentiment feature family (Tier routing — Phase 1 minimal)

**Files:**
- Create: `src/crypto_predictor/features/families/sentiment.py`
- Create: `tests/features/families/test_sentiment.py`

> **Plan A scope note**: Sentiment fetch from external APIs (NewsAPI, LunarCrush, LLM-judge) happens in the **daily orchestrator** (Week 7). In Plan A we implement only the *feature shape* and a stub that pulls from a `sentiment_cache.db` table. The cache will be populated by the Week 7 fetcher. For Plan A and the backtest, sentiment values default to neutral (0) when the cache is empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_sentiment.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.families.sentiment import (
    compute_sentiment_features, write_sentiment_cache,
)
from crypto_predictor.features.fetcher import FeatureFetcher


def test_sentiment_returns_neutral_when_cache_empty(tmp_path: Path):
    cache = tmp_path / "sentiment_cache.db"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_sentiment_features(fetcher, "BTC-USDT-SWAP",
                                        cache_db=cache)
    assert feats["news_sent_24h"] == 0.0
    assert feats["social_sent_24h"] == 0.0
    assert feats["sent_velocity"] == 0.0
    assert feats["news_volume_z"] == 0.0


def test_sentiment_reads_from_cache_when_present(tmp_path: Path):
    cache = tmp_path / "sentiment_cache.db"
    asof = datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc)
    # Write a known sentiment row
    write_sentiment_cache(cache, "BTC-USDT-SWAP",
                          asof.isoformat(),
                          news_sent_24h=0.42,
                          social_sent_24h=0.18,
                          sent_velocity=0.05,
                          news_volume_z=1.2)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_sentiment_features(fetcher, "BTC-USDT-SWAP",
                                        cache_db=cache)
    assert feats["news_sent_24h"] == pytest.approx(0.42)
    assert feats["social_sent_24h"] == pytest.approx(0.18)
    assert feats["news_volume_z"] == pytest.approx(1.2)
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement sentiment family + cache**

```python
# src/crypto_predictor/features/families/sentiment.py
"""Family 5 — sentiment. Reads from sentiment_cache.db (filled by Week 7 fetcher)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from crypto_predictor.features.fetcher import FeatureFetcher

NEUTRAL = {
    "news_sent_24h": 0.0,
    "social_sent_24h": 0.0,
    "sent_velocity": 0.0,
    "news_volume_z": 0.0,
}

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_cache (
    symbol           TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    news_sent_24h    REAL,
    social_sent_24h  REAL,
    sent_velocity    REAL,
    news_volume_z    REAL,
    PRIMARY KEY (symbol, timestamp)
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)
    conn.commit()


def write_sentiment_cache(db: Path, symbol: str, timestamp: str,
                          *, news_sent_24h: float, social_sent_24h: float,
                          sent_velocity: float, news_volume_z: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO sentiment_cache VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, timestamp, news_sent_24h, social_sent_24h,
             sent_velocity, news_volume_z),
        )
        conn.commit()
    finally:
        conn.close()


def compute_sentiment_features(fetcher: FeatureFetcher, symbol: str,
                               *, cache_db: Path) -> dict[str, float]:
    """Read pre-cached sentiment for (symbol, asof). Returns neutral if missing."""
    if not cache_db.exists():
        return dict(NEUTRAL)
    conn = sqlite3.connect(str(cache_db))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT news_sent_24h, social_sent_24h, sent_velocity, news_volume_z "
            "FROM sentiment_cache "
            "WHERE symbol = ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, fetcher.asof.isoformat()),
        ).fetchone()
        if row is None:
            return dict(NEUTRAL)
        return {
            "news_sent_24h": row[0] or 0.0,
            "social_sent_24h": row[1] or 0.0,
            "sent_velocity": row[2] or 0.0,
            "news_volume_z": row[3] or 0.0,
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_sentiment.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/sentiment.py tests/features/families/test_sentiment.py
git commit -m "feat(features): family 5 sentiment — cache reader (fetcher in Week 7)"
git push
```

---

## Task 3.8: Cross-coin / global feature family

**Files:**
- Create: `src/crypto_predictor/features/families/global_ctx.py`
- Create: `tests/features/families/test_global_ctx.py`

> **Plan A scope note**: Like sentiment, the *fetch* of BTC dominance / total mcap / sector indices uses live MCP servers (crypto-data MCP from trading-desk) and is wired up in Week 7. Plan A implements the feature shape + a cache reader.

- [ ] **Step 1: Write the failing test**

```python
# tests/features/families/test_global_ctx.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.families.global_ctx import (
    compute_global_features, write_global_cache,
)
from crypto_predictor.features.fetcher import FeatureFetcher


def test_global_returns_neutral_when_cache_empty(tmp_path: Path):
    cache = tmp_path / "global_cache.db"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_global_features(fetcher, "BTC-USDT-SWAP",
                                     cache_db=cache)
    for k in ["btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z",
              "sector_strength_24h", "coin_btc_corr_30d"]:
        assert feats[k] == 0.0


def test_global_reads_from_cache_when_present(tmp_path: Path):
    cache = tmp_path / "global_cache.db"
    asof = datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc)
    write_global_cache(cache, asof.isoformat(),
                       btc_dom_trend_7d=0.012,
                       eth_btc_trend_7d=-0.005,
                       total_mcap_z=1.4,
                       sector_btc=0.02, sector_eth=0.03,
                       sector_defi=-0.01, sector_l1=0.0)
    # Per-coin features additionally need a coin-specific row
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    feats = compute_global_features(fetcher, "BTC-USDT-SWAP",
                                     cache_db=cache, sector="btc")
    assert feats["btc_dom_trend_7d"] == pytest.approx(0.012)
    assert feats["sector_strength_24h"] == pytest.approx(0.02)
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement global family**

```python
# src/crypto_predictor/features/families/global_ctx.py
"""Family 6 — cross-coin / global context. Reads from global_cache.db."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from crypto_predictor.features.fetcher import FeatureFetcher

NEUTRAL = {
    "btc_dom_trend_7d": 0.0,
    "eth_btc_trend_7d": 0.0,
    "total_mcap_z": 0.0,
    "sector_strength_24h": 0.0,
    "coin_btc_corr_30d": 0.0,
}

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS global_cache (
    timestamp         TEXT PRIMARY KEY,
    btc_dom_trend_7d  REAL,
    eth_btc_trend_7d  REAL,
    total_mcap_z      REAL,
    sector_btc        REAL,
    sector_eth        REAL,
    sector_defi       REAL,
    sector_l1         REAL
);

CREATE TABLE IF NOT EXISTS coin_btc_corr (
    symbol     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    corr_30d   REAL,
    PRIMARY KEY (symbol, timestamp)
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)
    conn.commit()


def write_global_cache(db: Path, timestamp: str,
                       *, btc_dom_trend_7d: float, eth_btc_trend_7d: float,
                       total_mcap_z: float, sector_btc: float,
                       sector_eth: float, sector_defi: float,
                       sector_l1: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO global_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, btc_dom_trend_7d, eth_btc_trend_7d, total_mcap_z,
             sector_btc, sector_eth, sector_defi, sector_l1),
        )
        conn.commit()
    finally:
        conn.close()


def write_coin_corr(db: Path, symbol: str, timestamp: str,
                    corr_30d: float) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO coin_btc_corr VALUES (?, ?, ?)",
            (symbol, timestamp, corr_30d),
        )
        conn.commit()
    finally:
        conn.close()


def compute_global_features(fetcher: FeatureFetcher, symbol: str,
                            *, cache_db: Path, sector: str = "l1") -> dict[str, float]:
    """Pull global + coin-specific context features from cache.

    `sector` is one of {'btc','eth','defi','l1'} — caller knows the coin's bucket.
    """
    if not cache_db.exists():
        return dict(NEUTRAL)
    conn = sqlite3.connect(str(cache_db))
    try:
        _ensure_schema(conn)
        g = conn.execute(
            "SELECT btc_dom_trend_7d, eth_btc_trend_7d, total_mcap_z, "
            "       sector_btc, sector_eth, sector_defi, sector_l1 "
            "FROM global_cache WHERE timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (fetcher.asof.isoformat(),),
        ).fetchone()
        if g is None:
            global_out = dict(NEUTRAL)
        else:
            sector_map = {"btc": g[3], "eth": g[4], "defi": g[5], "l1": g[6]}
            global_out = {
                "btc_dom_trend_7d": g[0] or 0.0,
                "eth_btc_trend_7d": g[1] or 0.0,
                "total_mcap_z": g[2] or 0.0,
                "sector_strength_24h": sector_map.get(sector, 0.0) or 0.0,
            }
        c = conn.execute(
            "SELECT corr_30d FROM coin_btc_corr "
            "WHERE symbol = ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, fetcher.asof.isoformat()),
        ).fetchone()
        global_out["coin_btc_corr_30d"] = (c[0] if c else 0.0) or 0.0
        return global_out
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/families/test_global_ctx.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/families/global_ctx.py tests/features/families/test_global_ctx.py
git commit -m "feat(features): family 6 global context — cache reader (fetcher in Week 7)"
git push
```

---

## Task 3.9: Sector classifier (which sector does a coin belong to?)

**Files:**
- Create: `data/sector_map.yaml`
- Create: `src/crypto_predictor/features/sector_map.py`
- Create: `tests/features/test_sector_map.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_sector_map.py
from pathlib import Path

import yaml

from crypto_predictor.features.sector_map import classify_sector


def test_classify_btc_returns_btc(tmp_path: Path):
    yfile = tmp_path / "sector_map.yaml"
    yfile.write_text(yaml.safe_dump({
        "btc": ["BTC-USDT-SWAP"],
        "eth": ["ETH-USDT-SWAP"],
        "defi": ["AAVE-USDT-SWAP", "UNI-USDT-SWAP"],
        "l1": ["SOL-USDT-SWAP", "AVAX-USDT-SWAP"],
    }))
    assert classify_sector("BTC-USDT-SWAP", yfile) == "btc"
    assert classify_sector("AAVE-USDT-SWAP", yfile) == "defi"


def test_unknown_coin_returns_l1_default(tmp_path: Path):
    yfile = tmp_path / "sector_map.yaml"
    yfile.write_text(yaml.safe_dump({"btc": ["BTC-USDT-SWAP"]}))
    assert classify_sector("ZZZ-USDT-SWAP", yfile) == "l1"
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement sector_map module + seed YAML**

```python
# src/crypto_predictor/features/sector_map.py
"""Sector classification: which family does a coin belong to."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=4)
def _load(path: Path) -> dict[str, list[str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def classify_sector(symbol: str, sector_map_path: Path) -> str:
    """Return 'btc'|'eth'|'defi'|'l1' (default 'l1' if unknown)."""
    m = _load(sector_map_path)
    for sector, coins in m.items():
        if symbol in coins:
            return sector
    return "l1"
```

```yaml
# data/sector_map.yaml — Phase 1 seed; expand as needed
btc:
  - BTC-USDT-SWAP
eth:
  - ETH-USDT-SWAP
defi:
  - AAVE-USDT-SWAP
  - UNI-USDT-SWAP
  - CRV-USDT-SWAP
  - MKR-USDT-SWAP
  - SUSHI-USDT-SWAP
  - COMP-USDT-SWAP
  - SNX-USDT-SWAP
  - LDO-USDT-SWAP
  - 1INCH-USDT-SWAP
l1:
  - SOL-USDT-SWAP
  - AVAX-USDT-SWAP
  - DOT-USDT-SWAP
  - ATOM-USDT-SWAP
  - NEAR-USDT-SWAP
  - APT-USDT-SWAP
  - SUI-USDT-SWAP
  - ADA-USDT-SWAP
  - BNB-USDT-SWAP
  - TRX-USDT-SWAP
  # … unknown coins default to 'l1' via classify_sector fallback
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/test_sector_map.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/sector_map.py tests/features/test_sector_map.py data/sector_map.yaml
git commit -m "feat(features): sector classifier with seed YAML"
git push
```

---

## Task 3.10: mcap_rank_weight helper

**Files:**
- Create: `src/crypto_predictor/features/mcap_weight.py`
- Create: `tests/features/test_mcap_weight.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_mcap_weight.py
import pytest

from crypto_predictor.features.mcap_weight import mcap_rank_weight


def test_top_100_returns_full_weight():
    assert mcap_rank_weight(rank=1) == 1.0
    assert mcap_rank_weight(rank=50) == 1.0
    assert mcap_rank_weight(rank=100) == 1.0


def test_mid_tier_returns_seven_tenths():
    assert mcap_rank_weight(rank=101) == 0.7
    assert mcap_rank_weight(rank=200) == 0.7


def test_long_tail_returns_four_tenths():
    assert mcap_rank_weight(rank=201) == 0.4
    assert mcap_rank_weight(rank=340) == 0.4


def test_unknown_rank_returns_four_tenths():
    assert mcap_rank_weight(rank=None) == 0.4
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement helper**

```python
# src/crypto_predictor/features/mcap_weight.py
"""Sentiment dampener by mcap rank (top 100 = full trust, smaller = attenuated)."""
from __future__ import annotations


def mcap_rank_weight(rank: int | None) -> float:
    if rank is None:
        return 0.4
    if rank <= 100:
        return 1.0
    if rank <= 200:
        return 0.7
    return 0.4
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/test_mcap_weight.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/mcap_weight.py tests/features/test_mcap_weight.py
git commit -m "feat(features): mcap_rank_weight tier mapping"
git push
```

---

## Task 3.11: compute_features() orchestrator

**Files:**
- Create: `src/crypto_predictor/features/compute.py`
- Create: `tests/features/test_compute.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_compute.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher


def _seed_minimal_history(root: Path, symbol: str) -> None:
    df = pd.DataFrame([
        {"timestamp": 1700000000000 + i * 3600 * 1000, "open": 100, "high": 101,
         "low": 99, "close": 100 + (i % 5) * 0.1, "volume": 1000}
        for i in range(3000)
    ])
    write_ohlcv(root, symbol, "1h", df)
    for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
        n = max(60, 90 * (3600 // step) if step <= 3600 else 90 * (86400 // step))
        d = pd.DataFrame([
            {"timestamp": 1700000000000 + i * step * 1000, "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000}
            for i in range(n)
        ])
        write_ohlcv(root, symbol, tf, d)
    # empty futures parquets so fetcher returns empty frames cleanly
    for kind in ["funding", "oi", "ls_ratio", "liq"]:
        p = parquet_path(root, symbol, kind, "futures")
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_parquet(p, index=False)


def test_compute_features_returns_full_30_feature_dict(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_minimal_history(tmp_path, sym)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("btc:\n  - BTC-USDT-SWAP\n")
    asof = datetime.fromtimestamp(
        (1700000000000 + 2900 * 3600 * 1000) / 1000, tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)

    feats = compute_features(
        fetcher=fetcher,
        symbol=sym,
        sentiment_cache=tmp_path / "sentiment_cache.db",
        global_cache=tmp_path / "global_cache.db",
        sector_map_path=sector_map,
        mcap_rank=1,
    )
    expected_keys = {
        # momentum (6)
        "ret_15m_z", "ret_1h_z", "ret_4h_z", "ret_24h_z", "ret_7d_z",
        "mom_consistency",
        # perp (9)
        "funding_z", "funding_extreme", "oi_growth_24h", "oi_growth_z",
        "ls_ratio", "ls_ratio_change_4h", "taker_buy_sell_1h",
        "liq_pressure_long_4h", "liq_pressure_short_4h",
        # volume (1, rest deferred)
        "vol_z_24h",
        # technical (6)
        "rsi_14_1h", "rsi_overbought", "rsi_oversold", "macd_hist_1h",
        "bb_position_1h", "price_vs_sma50",
        # sentiment (4)
        "news_sent_24h", "social_sent_24h", "sent_velocity", "news_volume_z",
        # global (5)
        "btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z",
        "sector_strength_24h", "coin_btc_corr_30d",
        # meta (1)
        "mcap_rank_weight",
    }
    assert expected_keys.issubset(set(feats.keys())), \
        f"missing: {expected_keys - set(feats.keys())}"


def test_compute_features_under_500ms(tmp_path: Path):
    import time
    sym = "BTC-USDT-SWAP"
    _seed_minimal_history(tmp_path, sym)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("btc:\n  - BTC-USDT-SWAP\n")
    asof = datetime.fromtimestamp(
        (1700000000000 + 2900 * 3600 * 1000) / 1000, tz=timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    t0 = time.perf_counter()
    compute_features(
        fetcher=fetcher, symbol=sym,
        sentiment_cache=tmp_path / "sentiment_cache.db",
        global_cache=tmp_path / "global_cache.db",
        sector_map_path=sector_map,
        mcap_rank=1,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500, f"too slow: {elapsed_ms:.0f}ms"
```

- [ ] **Step 2: Run test, verify FAIL**

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement orchestrator**

```python
# src/crypto_predictor/features/compute.py
"""compute_features() — orchestrate all 6 families into one dict per coin."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.features.families.global_ctx import compute_global_features
from crypto_predictor.features.families.momentum import compute_momentum_features
from crypto_predictor.features.families.perp import compute_perp_features
from crypto_predictor.features.families.sentiment import compute_sentiment_features
from crypto_predictor.features.families.technical import compute_technical_features
from crypto_predictor.features.families.volume import compute_volume_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.mcap_weight import mcap_rank_weight
from crypto_predictor.features.sector_map import classify_sector


def compute_features(*, fetcher: FeatureFetcher, symbol: str,
                     sentiment_cache: Path, global_cache: Path,
                     sector_map_path: Path,
                     mcap_rank: int | None) -> dict[str, float]:
    """Compute all ~30 features for one (symbol, asof) into a flat dict."""
    sector = classify_sector(symbol, sector_map_path)
    feats: dict[str, float] = {}
    feats.update(compute_momentum_features(fetcher, symbol))
    feats.update(compute_perp_features(fetcher, symbol))
    feats.update(compute_volume_features(fetcher, symbol))
    feats.update(compute_technical_features(fetcher, symbol))
    feats.update(compute_sentiment_features(fetcher, symbol,
                                             cache_db=sentiment_cache))
    feats.update(compute_global_features(fetcher, symbol,
                                          cache_db=global_cache,
                                          sector=sector))
    feats["mcap_rank_weight"] = mcap_rank_weight(mcap_rank)
    return feats
```

- [ ] **Step 4: Run tests, verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/features/test_compute.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/crypto_predictor/features/compute.py tests/features/test_compute.py
git commit -m "feat(features): compute_features() orchestrator — 6 families + meta"
git push
```

---

## Task 3.12: Plan A integration test — full feature pipeline on real BTC data

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_plan_a_integration.py`

> **Prerequisite**: bulk ingest (Task 2.7) must have completed at least for BTC-USDT-SWAP. This test reads from the real `data/history/` parquet, NOT synthetic.

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_plan_a_integration.py
"""End-to-end Plan A integration test — real parquet, compute full feature dict."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC-USDT-SWAP" / "1h.parquet").exists(),
    reason="bulk ingest (Task 2.7) has not completed; skipping integration test",
)
def test_full_feature_dict_for_btc_real_data():
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=HISTORY_ROOT, asof=asof)
    feats = compute_features(
        fetcher=fetcher,
        symbol="BTC-USDT-SWAP",
        sentiment_cache=HISTORY_ROOT.parent / "sentiment_cache.db",
        global_cache=HISTORY_ROOT.parent / "global_cache.db",
        sector_map_path=SECTOR_MAP,
        mcap_rank=1,
    )
    assert len(feats) >= 25, f"expected ≥25 features, got {len(feats)}: {list(feats.keys())}"
    # Spot-check: all values numeric, no NaN
    import math
    for k, v in feats.items():
        assert isinstance(v, (int, float)), f"{k} is {type(v).__name__}"
        assert not math.isnan(v), f"{k} is NaN"
```

- [ ] **Step 2: Run integration test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/ -v
```

Expected: 1 test passes (or skipped if Task 2.7 not yet done — that's OK).

- [ ] **Step 3: Full test suite check**

```powershell
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```

Expected: ~30 tests, all green or only the integration test skipped pending Task 2.7.

- [ ] **Step 4: Commit**

```powershell
git add tests/integration/
git commit -m "test(integration): Plan A end-to-end feature pipeline on real BTC data"
git push
```

---

## Plan A complete — handoff to Plan B

✅ **What we have at end of Plan A:**

| Capability | Status |
|---|---|
| Plugin registered with Claude Code, `/predict ping` works | ✓ |
| 6 months of OKX-Global perp history in Parquet | ✓ |
| Resumable ingest script | ✓ |
| FeatureFetcher with strict asof-guard (look-ahead-bias prevention) | ✓ |
| ~30-feature pipeline working end-to-end | ✓ |
| z-score normalization with edge cases handled | ✓ |
| Sector classification + mcap weighting | ✓ |
| Sentiment + global caches scaffolded (fetchers in Week 7) | ✓ |
| ~30 unit + 1 integration test, all green | ✓ |

❌ **What Plan A does NOT yet do:**
- Generate any predictions (no direction formula, no calibration — Plan B)
- Run any backtest (Plan B)
- Have any LLM in the loop (Plan C)
- Validate any prediction (Plan D)
- Send any Telegram alert (Plan C/D)

---

**Next step:** When all Plan A tasks are checked off, return to brainstorming context and request Plan B (Weeks 4–6 — model layer: heuristic formula + magnitude + regime + anomaly + backtest framework + calibration). Plan B will be written with concrete Plan A feature names so signatures align.

**Suggested checkpoint**: after Plan A completion, run a quick sanity report:

```powershell
.\.venv\Scripts\python.exe -m pytest -v --tb=short
.\.venv\Scripts\python.exe scripts\verify_ingest.py --root data\history
```

Save the output to `docs/plans/2026-XX-XX-plan-a-completion-report.md` and ping me — I'll write Plan B against the actual feature behaviour you observed.

---

*End of Plan A.*
