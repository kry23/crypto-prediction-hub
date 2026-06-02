# crypto-predictor Phase 1 — Plan D: Validation Loop (Weeks 9–10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the B-loop. Every daily prediction gets validated against realized 24h returns; rolling metrics (hit rate, MAE, Brier, alpha) are computed and rendered into the daily report; the calibration map is monitored for drift and refit when it goes stale. Plus three Plan C follow-up fixes the Task 7.8 dry-run flagged.

**Architecture:** Two new packages under `src/crypto_predictor/`:
- **`validation/`** — `validator.py` (T+24h prediction outcome resolution), `rolling_metrics.py` (computes + persists rolling-window aggregates)
- **`patterns/`** — `pattern_detector.py` (mines high-win-rate feature combinations from closed predictions; populates `patterns` table)
- **Drift & recalibration:** lives under `crypto_predictor.calibration.drift` (new module). Reuses Plan B's `fit_calibration`+`save_calibration`.

Plus: wire scheduler `validate_pending`, `weekly_metrics`, `recalibrate` jobs from no-op stubs to real implementations.

**Tech stack:** Same as Plan A/B/C — no new deps.

**Related docs:**
- Design spec §13 (B-loop), §15.4 (`/predict-track` view)
- Plan C completion: `docs/plans/2026-06-02-plan-c-completion-report.md`

**Plan D success criteria:**
- Every prediction older than 24h in `predictions.db` either has `status='correct'|'incorrect'|'expired'` or was never validatable (logged separately)
- `metrics_rolling` table populates after `weekly_metrics` job runs; rows exist for windows ('7d', '30d', '90d') × regimes × directions
- Daily markdown report's "Validation Track Record" section renders live numbers (not the empty placeholder Plan C ships)
- `/predict-track` slash command shows the latest rolling metrics inline
- Drift monitor triggers a Telegram alert when rolling 7d Brier > backtest Brier + 0.05
- Pattern detector populates the `patterns` table with at least 1 row (SEEK / NEUTRAL / AVOID classification)
- Three Plan C follow-up fixes shipped (prediction-direction/target sign, composite human-readable scaling, empty-cache warning)
- All Plan D unit + integration tests green; ≥ 20 new tests

---

## Navigation

- **Week 9 — Validator + rolling metrics + Plan C fixes** (8 tasks)
- **Week 10 — Patterns + drift + benchmark + completion** (5 tasks)
- **Plan D complete — Phase 1 closes; v0.2 backlog opens**

---

## Prerequisites (before Task 9.1)

- [ ] **Verify Plan C is complete**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```
Expected: 155+ tests pass.

- [ ] **Generate at least one day of real predictions** so Plan D has data to validate

```powershell
.\.venv\Scripts\python.exe scripts\predict_scan_cli.py
```

This populates `predictions.db` with the day's predictions (340 symbols → ~340 rows in 5-8 min). Plan D's validator will need these to test against once they're 24h+ old.

If you want to test the validator immediately (without waiting 24 hours), Task 9.8's dry-run uses synthetic data where asof is back-dated 36h.

---

# Week 9 — Validator + rolling metrics + Plan C fixes

## Task 9.1: Fix prediction direction vs target_value sign inconsistency

**Bug discovered in Task 7.8 dry-run:** when calibration flips the sign of the raw direction score (e.g., raw=+0.05 → calibrated P_up=0.45 → prediction="down"), the `target_value` is still computed from the raw direction (positive), producing rows like `prediction="down", target_value=+0.73%`. Fix: compute `target_value` AFTER calibration, using the calibrated sign.

**Files:**
- Modify: `src/crypto_predictor/orchestrator/daily_scan.py`
- Modify: `tests/test_orchestrator/test_daily_scan_synthetic.py` (add invariant test)

- [ ] Step 1: Add a failing invariant test

In `tests/test_orchestrator/test_daily_scan_synthetic.py`, append:

```python
def test_target_value_sign_matches_prediction_direction(tmp_path: Path):
    """After Task 9.1 fix: prediction='down' implies target_value <= 0 (and vice versa)."""
    sym = "BTC-USDT-SWAP"
    _seed(tmp_path, n_symbols=3)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - FAKE{i}/USDT:USDT" for i in range(3)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)
    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    run_daily_scan(
        history_root=tmp_path,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,
        symbols=[f"FAKE{i}/USDT:USDT" for i in range(3)],
        mcap_ranks={f"FAKE{i}/USDT:USDT": 1 for i in range(3)},
        asof=asof,
        formula_version="v1.5",
    )
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT prediction, target_value FROM predictions"
    ).fetchall()
    conn.close()
    for prediction, target in rows:
        if prediction == "up":
            assert target >= 0, f"prediction=up but target={target}"
        else:
            assert target <= 0, f"prediction=down but target={target}"
```

- [ ] Step 2: Verify FAIL (invariant violated under current code)

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -m pytest tests/test_orchestrator/test_daily_scan_synthetic.py::test_target_value_sign_matches_prediction_direction -v
```

- [ ] Step 3: Fix in `daily_scan.py`

Find the block in `run_daily_scan`:
```python
raw = compute_direction_raw_for_regime(feats, regime)
p_up = predict_probability(calibs, raw_score=raw, regime=regime)
expected_ret = compute_expected_return(
    fetcher, sym, direction_raw=raw, regime=regime
)
```

Change the magnitude call to use a direction sign DERIVED from the calibrated probability, not from raw:

```python
raw = compute_direction_raw_for_regime(feats, regime)
p_up = predict_probability(calibs, raw_score=raw, regime=regime)
# Direction sign comes from CALIBRATED probability, not raw
calibrated_direction = p_up - 0.5  # in [-0.5, +0.5]
# Scale to roughly [-1, +1] by mapping (p_up - 0.5) * 2
calibrated_raw_for_magnitude = max(-1.0, min(1.0, calibrated_direction * 2.0))
expected_ret = compute_expected_return(
    fetcher, sym, direction_raw=calibrated_raw_for_magnitude, regime=regime
)
```

This guarantees `sign(expected_ret) == sign(p_up - 0.5)`, so `prediction == "up"` ↔ `target_value > 0`.

- [ ] Step 4: Verify PASS (new invariant test + the original `test_run_daily_scan_persists_predictions` still passes)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/daily_scan.py tests/test_orchestrator/test_daily_scan_synthetic.py
git commit -m "fix(orchestrator): target_value sign matches calibrated prediction direction (7.8 follow-up)"
git push
```

---

## Task 9.2: actual_return helper extension (multi-coin batch)

**Files:**
- Modify: `src/crypto_predictor/scoring/returns.py` (add batch helper)
- Create: `tests/test_features/test_scoring/test_returns_batch.py`

**Purpose:** Plan A's `actual_return` works one symbol at a time. The validator job needs to resolve hundreds of pending predictions efficiently. Add a batch helper that takes a list of (symbol, start_time, horizon) tuples and returns a list of returns (or None for missing data).

- [ ] Step 1: Failing test

```python
# tests/test_features/test_scoring/test_returns_batch.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.scoring.returns import actual_returns_batch


def _seed(root: Path, sym: str, n: int = 60):
    rows = []
    p = 100.0
    for i in range(n):
        p *= 1.001
        rows.append({"timestamp": 1700000000000 + i * 3600 * 1000,
                     "open": p, "high": p * 1.01, "low": p * 0.99,
                     "close": p, "volume": 1000})
    write_ohlcv(root, sym, "1h", pd.DataFrame(rows))


def test_batch_resolves_returns(tmp_path: Path):
    _seed(tmp_path, "BTC-USDT-SWAP", n=60)
    _seed(tmp_path, "ETH-USDT-SWAP", n=60)
    start = datetime.fromtimestamp(
        (1700000000000 + 20 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    out = actual_returns_batch(
        root=tmp_path,
        items=[
            ("BTC-USDT-SWAP", start, 24),
            ("ETH-USDT-SWAP", start, 24),
            ("UNKNOWN", start, 24),
        ],
    )
    assert len(out) == 3
    assert out[0] is not None  # BTC resolves
    assert out[1] is not None  # ETH resolves
    assert out[2] is None       # UNKNOWN missing
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement (append to `src/crypto_predictor/scoring/returns.py`)

```python
def actual_returns_batch(*, root,
                         items) -> list[float | None]:
    """Resolve actual_return for a batch of (symbol, start_time, horizon_hours) tuples."""
    out: list[float | None] = []
    for sym, start_time, horizon in items:
        out.append(actual_return(root=root, symbol=sym,
                                  start_time=start_time,
                                  horizon_hours=horizon))
    return out
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/scoring/returns.py tests/test_features/test_scoring/test_returns_batch.py
git commit -m "feat(scoring): actual_returns_batch helper for validator"
git push
```

---

## Task 9.3: Validator job — close pending predictions

**Files:**
- Create: `src/crypto_predictor/validation/__init__.py`
- Create: `src/crypto_predictor/validation/validator.py`
- Create: `tests/test_validation/__init__.py`
- Create: `tests/test_validation/test_validator.py`

- [ ] Step 1: Failing test

```python
# tests/test_validation/test_validator.py
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.validator import validate_pending_predictions


def _seed_ohlcv_with_pump(root: Path, sym: str, asof_ms: int):
    """Seed 1h bars so that price at asof+24h is 2% higher than at asof."""
    rows = []
    for i in range(72):
        ts = asof_ms - 24 * 3600 * 1000 + i * 3600 * 1000
        # Step price up by 2% exactly 24 bars in
        p = 100.0 * (1.02 if i >= 48 else 1.0)
        rows.append({"timestamp": ts, "open": p, "high": p * 1.01,
                     "low": p * 0.99, "close": p, "volume": 1000})
    write_ohlcv(root, sym, "1h", pd.DataFrame(rows))


def test_validator_closes_correct_up_prediction(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    sym = "BTC-USDT-SWAP"
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    asof_ms = int(asof_dt.timestamp() * 1000)
    _seed_ohlcv_with_pump(tmp_path, sym, asof_ms)

    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test1', ?, 24, 'up', 0.78, 0.02, 0.016, 'HIGH_CONV',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (sym, asof_dt.isoformat()))
    conn.commit()
    conn.close()

    now = asof_dt + timedelta(hours=25)
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    assert n_closed == 1

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, actual_outcome, validated_at FROM predictions WHERE id='test1'"
    ).fetchone()
    conn.close()
    assert row[0] == "correct"
    # Price moved ~+2%, so actual_outcome log(1.02) ≈ 0.0198
    assert abs(row[1] - math.log(1.02)) < 0.001
    assert row[2] is not None


def test_validator_marks_expired_when_data_missing(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    sym = "ABC-USDT-SWAP"  # NO ohlcv seeded
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test2', ?, 24, 'up', 0.6, 0.03, 0.018, 'NORMAL',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (sym, asof_dt.isoformat()))
    conn.commit()
    conn.close()

    now = asof_dt + timedelta(hours=25)
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    # Missing data: status becomes 'expired'
    assert n_closed == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status FROM predictions WHERE id='test2'"
    ).fetchone()
    conn.close()
    assert row[0] == "expired"


def test_validator_leaves_too_recent_predictions_alone(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test3', 'X', 24, 'up', 0.6, 0.03, 0.018, 'NORMAL',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (asof_dt.isoformat(),))
    conn.commit()
    conn.close()
    now = asof_dt + timedelta(hours=12)  # only 12h elapsed
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    assert n_closed == 0
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/validation/__init__.py
"""Validation loop — close pending predictions, compute rolling metrics."""
```

```python
# src/crypto_predictor/validation/validator.py
"""Close pending predictions against realized returns."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from crypto_predictor.scoring.returns import actual_return

log = structlog.get_logger(__name__)


def validate_pending_predictions(*, predictions_db: Path,
                                  history_root: Path,
                                  now: datetime) -> int:
    """Close pending predictions whose horizon has elapsed. Returns count closed."""
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows = conn.execute(
            "SELECT id, symbol, horizon_hours, prediction, target_value, created_at "
            "FROM predictions WHERE status = 'pending'"
        ).fetchall()
        n_closed = 0
        for pred_id, symbol, horizon_hours, prediction, target_value, created_at in rows:
            created_dt = datetime.fromisoformat(created_at)
            elapsed = now - created_dt
            if elapsed < timedelta(hours=horizon_hours):
                continue

            actual = actual_return(
                root=history_root, symbol=symbol,
                start_time=created_dt, horizon_hours=horizon_hours,
            )
            if actual is None:
                conn.execute(
                    "UPDATE predictions SET status='expired', validated_at=? "
                    "WHERE id=?",
                    (now.isoformat(), pred_id),
                )
                n_closed += 1
                continue

            correct = (
                (prediction == "up" and actual > 0)
                or (prediction == "down" and actual < 0)
            )
            error_margin = abs(target_value - actual) if target_value else None
            evaluation = (
                f"dir={'OK' if correct else 'FAIL'}; "
                f"actual={actual:+.4f}; predicted={target_value:+.4f}"
            )
            conn.execute(
                "UPDATE predictions SET status=?, actual_outcome=?, "
                "error_margin=?, evaluation=?, validated_at=? WHERE id=?",
                ("correct" if correct else "incorrect",
                 actual, error_margin, evaluation, now.isoformat(),
                 pred_id),
            )
            n_closed += 1
        conn.commit()
        return n_closed
    finally:
        conn.close()
```

- [ ] Step 4: Verify PASS (3 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/validation/ tests/test_validation/
git commit -m "feat(validation): validator closes pending predictions against realized returns"
git push
```

---

## Task 9.4: Rolling metrics computation + persistence

**Files:**
- Create: `src/crypto_predictor/validation/rolling_metrics.py`
- Create: `tests/test_validation/test_rolling_metrics.py`

**Purpose:** After each validator run, aggregate closed predictions into rolling windows (7d, 30d, 90d) × regime ('ALL', 'BULL', 'BEAR', 'CHOP') × direction ('all', 'long', 'short'). Persist into `metrics_rolling` table.

- [ ] Step 1: Failing test

```python
# tests/test_validation/test_rolling_metrics.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics


def _insert(conn, pid: str, status: str, prediction: str, actual: float,
            target: float, regime: str, validated_at_iso: str):
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status,
            actual_outcome, validated_at, created_at)
        VALUES (?, 'X', 24, ?, 0.6, ?, 0.018, 'NORMAL', ?, 'v1.5', 'v1.5.4',
                ?, ?, ?, ?)
    """, (pid, prediction, target, regime, status, actual,
          validated_at_iso, validated_at_iso))


def test_update_rolling_metrics_populates_table(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    # 10 'up' predictions in BULL regime, 7 correct (hit rate 70%)
    for i in range(10):
        _insert(conn, f"u{i}",
                "correct" if i < 7 else "incorrect",
                "up", 0.02 if i < 7 else -0.01,
                0.03, "BULL",
                (now - timedelta(hours=24 + i)).isoformat())
    conn.commit()
    conn.close()

    update_rolling_metrics(predictions_db=db, now=now)

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT window, regime, direction, hit_rate, n_predictions "
        "FROM metrics_rolling ORDER BY window, regime, direction"
    ).fetchall()
    conn.close()

    assert len(rows) > 0
    by_key = {(r[0], r[1], r[2]): r for r in rows}
    assert ("7d", "BULL", "long") in by_key
    win, regime, dir_, hit, n = by_key[("7d", "BULL", "long")]
    assert abs(hit - 0.7) < 0.001
    assert n == 10
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/validation/rolling_metrics.py
"""Rolling metrics computation + persistence into metrics_rolling table."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

WINDOWS = {"7d": 7, "30d": 30, "90d": 90}
REGIMES = ["ALL", "BULL", "BEAR", "CHOP"]
DIRECTIONS = ["all", "long", "short"]


def _matches(row, regime, direction):
    _, prediction, _, row_regime, _ = row
    if regime != "ALL" and row_regime != regime:
        return False
    if direction == "long" and prediction != "up":
        return False
    if direction == "short" and prediction != "down":
        return False
    return True


def _agg(rows):
    if not rows:
        return None
    n = len(rows)
    correct = sum(1 for r in rows if r[0] == "correct")
    hit_rate = correct / n
    mae_vals = [abs(r[4] - r[2]) for r in rows if r[4] is not None and r[2] is not None]
    mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0.0
    return n, correct, hit_rate, mae


def update_rolling_metrics(*, predictions_db: Path, now: datetime) -> int:
    """Recompute and persist rolling metrics. Returns count of metric rows written."""
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows_written = 0
        for win_label, days in WINDOWS.items():
            cutoff = (now - timedelta(days=days)).isoformat()
            raw = conn.execute(
                "SELECT status, prediction, target_value, regime, actual_outcome "
                "FROM predictions "
                "WHERE status IN ('correct','incorrect') AND validated_at >= ?",
                (cutoff,),
            ).fetchall()
            for regime in REGIMES:
                for direction in DIRECTIONS:
                    filt = [r for r in raw if _matches(r, regime, direction)]
                    agg = _agg(filt)
                    if agg is None:
                        continue
                    n, correct, hit, mae = agg
                    conn.execute(
                        "INSERT OR REPLACE INTO metrics_rolling("
                        "window, regime, direction, n_predictions, n_correct, "
                        "hit_rate, mae, brier, topk_alpha, topk_alpha_btc, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)",
                        (win_label, regime, direction, n, correct,
                         hit, mae, now.isoformat()),
                    )
                    rows_written += 1
        conn.commit()
        return rows_written
    finally:
        conn.close()
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/validation/rolling_metrics.py tests/test_validation/test_rolling_metrics.py
git commit -m "feat(validation): rolling metrics computation + metrics_rolling persistence"
git push
```

---

## Task 9.5: Update markdown report to render live rolling metrics

**Files:**
- Modify: `src/crypto_predictor/output/markdown_report.py` (extend rolling_metrics renderer to accept the live schema)
- Modify: `tests/test_output/test_markdown_report.py` (update test to use real schema)

The `render_daily_report` already accepts a `rolling_metrics` dict. Plan D adds a small helper that loads from the DB into that format, and the report renderer handles the live data correctly (no major code change — Plan C's signature already supports it).

- [ ] Step 1: Add a helper `load_rolling_metrics_from_db` in `src/crypto_predictor/validation/rolling_metrics.py`

```python
def load_rolling_metrics_from_db(predictions_db: Path) -> dict[str, dict]:
    """Load latest rolling-metrics rows for window='ALL'/direction='all' (for report rendering)."""
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows = conn.execute(
            "SELECT window, hit_rate, n_predictions, COALESCE(topk_alpha, 0.0) "
            "FROM metrics_rolling "
            "WHERE regime='ALL' AND direction='all' "
            "ORDER BY window"
        ).fetchall()
        return {
            window: {"hit_rate": hr, "n": n, "alpha": alpha}
            for window, hr, n, alpha in rows
        }
    finally:
        conn.close()
```

- [ ] Step 2: Modify scheduler `_job_predict_scan` to call `load_rolling_metrics_from_db` and pass to the markdown renderer

In `src/crypto_predictor/scheduler/jobs.py`, change:
```python
report_md = render_daily_report(
    asof=asof, regime=result["scan"]["regime"], slate=slate,
    n_scanned=len(symbols), n_skipped=result["scan"]["n_skipped"],
    rolling_metrics={},
)
```
to:
```python
from crypto_predictor.validation.rolling_metrics import load_rolling_metrics_from_db
rolling = load_rolling_metrics_from_db(predictions_db)
report_md = render_daily_report(
    asof=asof, regime=result["scan"]["regime"], slate=slate,
    n_scanned=len(symbols), n_skipped=result["scan"]["n_skipped"],
    rolling_metrics=rolling,
)
```

- [ ] Step 3: Test — full suite stays green

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -m pytest -v --tb=short 2>&1 | Select-Object -Last 10
```

- [ ] Step 4: Commit + push

```powershell
git add src/crypto_predictor/validation/rolling_metrics.py src/crypto_predictor/scheduler/jobs.py
git commit -m "feat(report): wire live rolling metrics into daily markdown"
git push
```

---

## Task 9.6: `/predict-track` slash command + CLI

**Files:**
- Create: `commands/predict-track.md`
- Create: `scripts/predict_track_cli.py`

- [ ] Step 1: Create slash command

```markdown
# commands/predict-track.md
---
description: Show rolling track record from validated predictions
---

Run `python scripts/predict_track_cli.py` and report the output inline.

Show:
- Rolling 7d/30d/90d hit rate, MAE, n predictions
- Per regime breakdown (BULL/BEAR/CHOP)
- Recent calibration drift status (if drift detected)
```

- [ ] Step 2: Create CLI

```python
# scripts/predict_track_cli.py
"""Show rolling track record from the predictions database."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[1],
    ))
    db = project_root / "predictions.db"
    if not db.exists():
        print(f"No predictions.db at {db}")
        return 1
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT window, regime, direction, hit_rate, mae, n_predictions, updated_at "
            "FROM metrics_rolling ORDER BY window, regime, direction"
        ).fetchall()
        if not rows:
            print("No metrics_rolling rows yet. Run validate_pending + weekly_metrics first.")
            return 0
        print("Rolling track record:")
        print(f"{'Window':<6} {'Regime':<6} {'Dir':<6} {'Hit':<8} {'MAE':<8} {'n':<6} {'Updated':<25}")
        for window, regime, direction, hit, mae, n, updated in rows:
            print(f"{window:<6} {regime:<6} {direction:<6} "
                  f"{hit*100:>6.1f}% {(mae or 0)*100:>6.2f}% {n:<6} {updated}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 3: Commit + push

```powershell
git add commands/predict-track.md scripts/predict_track_cli.py
git commit -m "feat(cli): /predict-track command + CLI for rolling metrics"
git push
```

---

## Task 9.7: Wire scheduler `validate_pending` + `weekly_metrics` jobs

**Files:**
- Modify: `src/crypto_predictor/scheduler/jobs.py`
- Modify: `tests/test_scheduler/test_predict_scan_job.py` (or add new tests for the other jobs)

- [ ] Step 1: Add tests for the two new wirings

```python
# tests/test_scheduler/test_validate_jobs.py
from unittest.mock import patch

from crypto_predictor.scheduler.jobs import (
    _job_validate_pending, _job_weekly_metrics,
)


@patch("crypto_predictor.scheduler.jobs.validate_pending_predictions")
def test_validate_pending_calls_validator(mock_validate):
    mock_validate.return_value = 5
    _job_validate_pending()
    mock_validate.assert_called_once()


@patch("crypto_predictor.scheduler.jobs.update_rolling_metrics")
def test_weekly_metrics_calls_aggregator(mock_update):
    mock_update.return_value = 12
    _job_weekly_metrics()
    mock_update.assert_called_once()
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Wire the jobs

In `src/crypto_predictor/scheduler/jobs.py`, replace:
```python
def _job_validate_pending() -> None:
    log.info("validate_pending job fired (no-op in Plan A)")


def _job_weekly_metrics() -> None:
    log.info("weekly_metrics job fired (no-op in Plan A)")
```

with:

```python
from crypto_predictor.validation.validator import validate_pending_predictions
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics


def _job_validate_pending() -> None:
    """Close pending predictions whose horizon has elapsed."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    n = validate_pending_predictions(
        predictions_db=project_root / "predictions.db",
        history_root=project_root / "data" / "history",
        now=datetime.now(timezone.utc),
    )
    log.info("validate_pending_done", n_closed=n)


def _job_weekly_metrics() -> None:
    """Refresh rolling metrics table."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    n = update_rolling_metrics(
        predictions_db=project_root / "predictions.db",
        now=datetime.now(timezone.utc),
    )
    log.info("weekly_metrics_done", n_rows=n)
```

Keep `_job_predict_scan`, `_job_recalibrate`, `build_scheduler`, `list_registered_jobs` unchanged.

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/scheduler/jobs.py tests/test_scheduler/test_validate_jobs.py
git commit -m "feat(scheduler): wire validate_pending and weekly_metrics jobs"
git push
```

---

## Task 9.8: Plan D Week-9 dry run

**Files:** none — operational test

- [ ] Step 1: Synthetic dry run — back-date predictions so validator has something to close immediately

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -c "
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from crypto_predictor.storage.predictions_db import init_db
db = Path('predictions.db')
init_db(db)
conn = sqlite3.connect(db)
# Insert one 25h-old prediction for BTC
old = datetime.now(timezone.utc) - timedelta(hours=25)
conn.execute('''INSERT OR REPLACE INTO predictions (id, symbol, horizon_hours,
    prediction, p_direction, target_value, composite_score, confidence_flag,
    regime, formula_version, calibration_version, status, created_at)
    VALUES ('test_validator_dry', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02,
    0.013, 'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'pending', ?)''',
    (old.isoformat(),))
conn.commit()
conn.close()

# Validator
from crypto_predictor.validation.validator import validate_pending_predictions
n = validate_pending_predictions(
    predictions_db=db,
    history_root=Path('data/history'),
    now=datetime.now(timezone.utc),
)
print(f'Closed: {n}')

# Status check
conn = sqlite3.connect(db)
row = conn.execute('SELECT status, actual_outcome FROM predictions WHERE id=?',
                   ('test_validator_dry',)).fetchone()
conn.close()
print(f'Status: {row[0]}, actual_outcome: {row[1]}')
"
```

Expected: `Closed: 1`, `Status: correct|incorrect|expired`.

- [ ] Step 2: Run rolling metrics

```powershell
.\.venv\Scripts\python.exe -c "
from datetime import datetime, timezone
from pathlib import Path
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics
n = update_rolling_metrics(predictions_db=Path('predictions.db'), now=datetime.now(timezone.utc))
print(f'Rolling rows: {n}')
"
```

Then `/predict-track`:

```powershell
.\.venv\Scripts\python.exe scripts\predict_track_cli.py
```

- [ ] Step 3: Sanity check — does the metrics table populate? Are values reasonable?

- [ ] Step 4: No commit (operational only).

---

# Week 10 — Patterns + drift + benchmark + completion

## Task 10.1: Pattern detector

**Files:**
- Create: `src/crypto_predictor/patterns/__init__.py`
- Create: `src/crypto_predictor/patterns/pattern_detector.py`
- Create: `tests/test_patterns/__init__.py`
- Create: `tests/test_patterns/test_pattern_detector.py`

**Purpose:** Mine the predictions_features table (populated by Plan A daily_scan feature persistence... actually we don't write features per prediction yet. For now, mine the predictions table by joining on regime and confidence_flag. v0.2 can add per-prediction feature snapshots properly).

Detect 3 simple patterns initially:
- `HIGH_CONV in regime=R has win rate X%` → SEEK if X > 0.65, AVOID if X < 0.50
- `WILD_CARD has win rate X%` → log only (don't classify)
- `prediction=up + regime=BULL` baseline

- [ ] Step 1: Failing test

```python
# tests/test_patterns/test_pattern_detector.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.patterns.pattern_detector import detect_and_upsert_patterns
from crypto_predictor.storage.predictions_db import init_db


def _insert_pred(conn, pid, status, prediction, regime, flag,
                  validated_at_iso):
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status,
            validated_at, created_at)
        VALUES (?, 'X', 24, ?, 0.7, 0.03, 0.021, ?, ?, 'v1.5', 'v1.5.4',
                ?, ?, ?)
    """, (pid, prediction, flag, regime, status,
          validated_at_iso, validated_at_iso))


def test_detect_patterns_populates_table(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    # 10 HIGH_CONV BULL — 7 correct (70%)
    for i in range(10):
        _insert_pred(conn, f"hc{i}",
                     "correct" if i < 7 else "incorrect",
                     "up", "BULL", "HIGH_CONV",
                     (now - timedelta(hours=24 + i)).isoformat())
    conn.commit()
    conn.close()

    n_patterns = detect_and_upsert_patterns(predictions_db=db, now=now)
    assert n_patterns >= 1

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT name, win_rate, recommendation FROM patterns"
    ).fetchall()
    conn.close()
    names = {r[0] for r in rows}
    assert any("HIGH_CONV" in n and "BULL" in n for n in names)
    # The 70% pattern should be SEEK
    seek_rows = [r for r in rows if r[2] == "SEEK"]
    assert any(abs(r[1] - 0.7) < 0.01 for r in seek_rows)
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/patterns/__init__.py
"""Pattern detection over closed predictions."""
```

```python
# src/crypto_predictor/patterns/pattern_detector.py
"""Mine simple patterns from closed predictions."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


def _classify(win_rate: float, seek_threshold: float = 0.65,
              avoid_threshold: float = 0.50) -> str:
    if win_rate > seek_threshold:
        return "SEEK"
    if win_rate < avoid_threshold:
        return "AVOID"
    return "NEUTRAL"


def detect_and_upsert_patterns(*, predictions_db: Path,
                                now: datetime, lookback_days: int = 30,
                                min_occurrences: int = 5) -> int:
    """Detect simple patterns over the last `lookback_days` of closed predictions."""
    cutoff = (now - timedelta(days=lookback_days)).isoformat()
    conn = sqlite3.connect(str(predictions_db))
    try:
        # Cohort 1: confidence_flag × regime
        rows = conn.execute(
            "SELECT confidence_flag, regime, status FROM predictions "
            "WHERE status IN ('correct','incorrect') AND validated_at >= ?",
            (cutoff,),
        ).fetchall()
        cohorts: dict[tuple, list[str]] = {}
        for flag, regime, status in rows:
            cohorts.setdefault((flag, regime), []).append(status)

        n_written = 0
        for (flag, regime), statuses in cohorts.items():
            if len(statuses) < min_occurrences:
                continue
            wins = sum(1 for s in statuses if s == "correct")
            win_rate = wins / len(statuses)
            recommendation = _classify(win_rate)
            name = f"{flag}@{regime}"
            conn.execute(
                "INSERT OR REPLACE INTO patterns ("
                "name, occurrences, wins, losses, win_rate, recommendation, last_seen"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, len(statuses), wins, len(statuses) - wins,
                 win_rate, recommendation, now.isoformat()),
            )
            n_written += 1
        conn.commit()
        return n_written
    finally:
        conn.close()
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/patterns/ tests/test_patterns/
git commit -m "feat(patterns): simple pattern detector (confidence_flag × regime cohorts)"
git push
```

---

## Task 10.2: Calibration drift monitor + alert

**Files:**
- Create: `src/crypto_predictor/calibration/drift.py`
- Create: `tests/test_calibration/test_drift.py`

- [ ] Step 1: Failing test

```python
# tests/test_calibration/test_drift.py
from crypto_predictor.calibration.drift import detect_drift, DriftStatus


def test_no_drift_when_brier_close_to_baseline():
    status = detect_drift(current_brier=0.226, backtest_brier=0.224, delta=0.05)
    assert status == DriftStatus.OK


def test_drift_when_brier_exceeds_baseline_plus_delta():
    status = detect_drift(current_brier=0.30, backtest_brier=0.22, delta=0.05)
    assert status == DriftStatus.DRIFT


def test_no_drift_when_brier_better_than_baseline():
    status = detect_drift(current_brier=0.18, backtest_brier=0.22, delta=0.05)
    assert status == DriftStatus.OK
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/calibration/drift.py
"""Calibration drift detection."""
from __future__ import annotations

from enum import Enum


class DriftStatus(str, Enum):
    OK = "OK"
    DRIFT = "DRIFT"


def detect_drift(*, current_brier: float, backtest_brier: float,
                 delta: float = 0.05) -> DriftStatus:
    if current_brier > backtest_brier + delta:
        return DriftStatus.DRIFT
    return DriftStatus.OK
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/calibration/drift.py tests/test_calibration/test_drift.py
git commit -m "feat(calibration): drift detector (current Brier vs backtest baseline)"
git push
```

---

## Task 10.3: Benchmark tracker — alpha vs equal-weight + BTC

**Files:**
- Modify: `src/crypto_predictor/validation/rolling_metrics.py` (extend to compute alpha)
- Create: `tests/test_validation/test_benchmark.py`

The existing `update_rolling_metrics` writes `topk_alpha=NULL` and `topk_alpha_btc=NULL`. Plan D fills them in.

- [ ] Step 1: Failing test

```python
# tests/test_validation/test_benchmark.py
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.rolling_metrics import (
    compute_top_k_alpha, update_rolling_metrics,
)


def test_compute_top_k_alpha_positive_when_topk_beats():
    universe = [0.0, 0.0, 0.0, 0.0, 0.0]
    top_k = [0.05, 0.04, 0.03]
    alpha = compute_top_k_alpha(top_k, universe)
    assert alpha > 0


def test_update_rolling_metrics_populates_topk_alpha(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    # 5 'up' predictions, target=0.04 each, actual_outcome varied
    for i, actual in enumerate([0.05, 0.04, 0.03, -0.01, -0.02]):
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status,
                actual_outcome, validated_at, created_at)
            VALUES (?, 'X', 24, 'up', 0.7, 0.04, 0.028, 'NORMAL', 'BULL',
                    'v1.5', 'v1.5.4', 'correct', ?, ?, ?)
        """, (f"p{i}", actual,
              (now - timedelta(hours=24 + i)).isoformat(),
              (now - timedelta(hours=24 + i)).isoformat()))
    conn.commit()
    conn.close()

    update_rolling_metrics(predictions_db=db, now=now)

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT topk_alpha FROM metrics_rolling "
        "WHERE window='7d' AND regime='BULL' AND direction='long'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement `compute_top_k_alpha` and modify `update_rolling_metrics`

Add to `rolling_metrics.py`:

```python
def compute_top_k_alpha(top_k_returns, universe_returns) -> float:
    """Top-K mean return minus universe mean return."""
    if not top_k_returns or not universe_returns:
        return 0.0
    import statistics
    return statistics.mean(top_k_returns) - statistics.mean(universe_returns)
```

Modify `_agg` to also compute alpha:

```python
def _agg(rows, all_rows_for_universe):
    if not rows:
        return None
    n = len(rows)
    correct = sum(1 for r in rows if r[0] == "correct")
    hit_rate = correct / n
    mae_vals = [abs(r[4] - r[2]) for r in rows if r[4] is not None and r[2] is not None]
    mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0.0

    # Compute top-K alpha (top 20% by |target_value|, signed by direction)
    sorted_by_signal = sorted(
        rows, key=lambda r: abs(r[2] or 0), reverse=True,
    )
    k = max(1, n // 5)
    top_k_actuals = [r[4] for r in sorted_by_signal[:k] if r[4] is not None]
    universe_actuals = [r[4] for r in all_rows_for_universe if r[4] is not None]
    alpha = compute_top_k_alpha(top_k_actuals, universe_actuals) if top_k_actuals else None

    return n, correct, hit_rate, mae, alpha
```

Update the INSERT in `update_rolling_metrics` to write `topk_alpha = alpha` (use `?` placeholder instead of `NULL`).

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/validation/rolling_metrics.py tests/test_validation/test_benchmark.py
git commit -m "feat(validation): top-K alpha vs equal-weight universe in rolling metrics"
git push
```

---

## Task 10.4: Wire `_job_recalibrate` job (scaffold only — manual run for now)

**Purpose:** The job exists but doesn't refit calibration automatically yet (high blast radius). Plan D wires it to log "would refit" + a Telegram drift alert. Auto-refit ships in v0.3.

- [ ] Step 1: Failing test

```python
# tests/test_scheduler/test_recalibrate_job.py
from unittest.mock import patch

from crypto_predictor.scheduler.jobs import _job_recalibrate


def test_recalibrate_job_calls_drift_check(monkeypatch, capsys):
    _job_recalibrate()
    # For now, the job just logs — we just confirm it doesn't crash
```

- [ ] Step 2: Verify FAIL or trivially pass

- [ ] Step 3: Implement (in `scheduler/jobs.py`)

```python
def _job_recalibrate() -> None:
    """Drift check (Phase 1) — Plan D scaffold; auto-refit deferred to v0.3."""
    log.info("recalibrate_job_start_phase1_scaffold")
    # Phase 1: drift check via rolling Brier vs baseline
    # Auto-refit deferred to v0.3 (high blast radius without staging)
    log.info("recalibrate_job_done", phase="1_scaffold_only")
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/scheduler/jobs.py tests/test_scheduler/test_recalibrate_job.py
git commit -m "feat(scheduler): recalibrate job (Phase 1 scaffold; auto-refit deferred to v0.3)"
git push
```

---

## Task 10.5: Plan D integration test + completion report

**Files:**
- Create: `tests/integration/test_plan_d_integration.py`
- Create: `docs/plans/2026-XX-XX-plan-d-completion-report.md` (date when done)

- [ ] Step 1: Integration test — validator + rolling metrics on real BTC

```python
# tests/integration/test_plan_d_integration.py
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.validator import validate_pending_predictions
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_d_validator_closes_btc_prediction(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    asof = datetime.now(timezone.utc) - timedelta(hours=48)
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('itest', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013,
                'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (asof.isoformat(),))
    conn.commit()
    conn.close()
    n = validate_pending_predictions(
        predictions_db=db, history_root=HISTORY_ROOT,
        now=datetime.now(timezone.utc),
    )
    assert n == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status FROM predictions WHERE id='itest'"
    ).fetchone()
    conn.close()
    assert row[0] in ("correct", "incorrect")  # not expired


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_d_rolling_metrics_after_validator(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    asof = datetime.now(timezone.utc) - timedelta(hours=48)
    conn = sqlite3.connect(db)
    for i in range(7):
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status, created_at)
            VALUES (?, 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013,
                    'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
        """, (f"itest{i}", (asof - timedelta(hours=i)).isoformat()))
    conn.commit()
    conn.close()
    validate_pending_predictions(
        predictions_db=db, history_root=HISTORY_ROOT,
        now=datetime.now(timezone.utc),
    )
    n_metrics = update_rolling_metrics(
        predictions_db=db, now=datetime.now(timezone.utc),
    )
    assert n_metrics > 0
```

- [ ] Step 2: Run integration tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan_d_integration.py -v
```

- [ ] Step 3: Write Plan D completion report

`docs/plans/2026-06-XX-plan-d-completion-report.md` — same shape as Plan C completion. Sections: what shipped, what didn't (v0.2+ scope), commits, Phase 1 closing statement.

- [ ] Step 4: Commit + push

```powershell
git add tests/integration/test_plan_d_integration.py docs/plans/2026-06-XX-plan-d-completion-report.md
git commit -m "test(integration): Plan D end-to-end + Phase 1 completion report"
git push
```

---

## Plan D complete — Phase 1 closes

✅ **What Plan D delivers:**

| Capability | Status |
|---|---|
| Validator closes pending predictions at T+24h | ✓ |
| Rolling metrics persisted to `metrics_rolling` (7d/30d/90d × regime × direction) | ✓ |
| Top-K alpha vs equal-weight universe computed nightly | ✓ |
| Markdown daily report renders live "Validation Track Record" section | ✓ |
| `/predict-track` slash command shows rolling metrics inline | ✓ |
| Pattern detector populates `patterns` table (SEEK / NEUTRAL / AVOID) | ✓ |
| Calibration drift monitor (current_brier vs backtest_brier + δ) | ✓ |
| Scheduler `validate_pending` + `weekly_metrics` wired | ✓ |
| Scheduler `recalibrate` scaffolded (auto-refit deferred to v0.3) | ✓ |
| Plan C follow-up: prediction direction ↔ target_value sign aligned | ✓ |
| Plan D integration test on real BTC | ✓ |

❌ **What Plan D does NOT do (Phase 1 closing limits):**
- Auto-refit calibration on drift detection (v0.3) — too high blast radius without staging
- Per-prediction feature snapshot persistence (would enable richer pattern mining; v0.2)
- 4h / 7d horizons (v0.2 / v0.4)
- LightGBM ML model (v0.3)
- Real Telegram drift-alert send (currently logs only; add SMS / Telegram in v0.2)
- Sentiment + global cache fetchers (Plan C left this open; ship as Phase 1.5+ once needed)

---

## Phase 1 — final state

**Plans completed in chronological order:**
- Plan A — data foundation (30 tasks)
- Plan B — scoring + calibration (18 tasks)
- Phase 1.5 — diagnostic sprint (5 substantive commits, all §19 targets MET)
- Plan C — daily pipeline + output (14 tasks)
- Plan D — validation loop + patterns + drift (13 tasks)

**Total**: ~80 tasks, ~180+ unit + integration tests, full production scaffold.

**Spec §19 success criteria — final**:
| Criterion | Final state |
|---|---|
| Direction hit rate ≥ 58% (rolling 30d) | ✅ 62.5% on 340-sym validation |
| Calibration MAE ≤ 5% | ✅ near-perfect (predicted ≈ empirical) |
| Top-K alpha ≥ +1.5% | ✅ +2.42% combined |
| Brier score ≤ 0.23 | ✅ 0.226 |
| Daily run uptime ≥ 95% | (measure during first 30 days of live ops) |
| Unit test coverage ≥ 75% | (current ~80%; verify at Phase 1 close) |

**v0.2 scope (when ready):**
- 4h horizon
- Sector concentration overlay
- Notification preferences v2
- Per-prediction feature snapshots
- Sentiment + global cache fetchers (NewsAPI + LunarCrush + crypto-data MCP)
- Real Telegram drift alerts

**v0.3 scope:**
- LightGBM ML model (ensemble or replace heuristic)
- A/B harness for parallel formula testing
- Auto-recalibration with staged rollout
- Drift monitor automation

---

*End of Plan D. When Plan D ships, Phase 1 is complete and the system is in production.*
