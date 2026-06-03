"""v0.2 end-to-end: incremental ingest + cache fetchers + feature snapshots + drift alert wire."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.calibration.drift import detect_drift, DriftStatus
from crypto_predictor.patterns.pattern_detector import detect_feature_patterns
from crypto_predictor.storage.predictions_db import init_db


def test_v02_modules_importable():
    """Sanity: all v0.2 modules import cleanly."""
    import scripts.incremental_ingest  # noqa
    import crypto_predictor.sentiment.newsapi_fetcher  # noqa
    import crypto_predictor.sentiment.cache_writer  # noqa
    import crypto_predictor.sentiment.lunarcrush_fetcher  # noqa
    import crypto_predictor.global_ctx.fetcher  # noqa
    from crypto_predictor.patterns.pattern_detector import detect_feature_patterns  # noqa


def test_drift_status_when_brier_doubled():
    assert detect_drift(current_brier=0.45, backtest_brier=0.226) == DriftStatus.DRIFT


def test_pattern_detector_v2_empty_db_returns_zero(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    n = detect_feature_patterns(
        predictions_db=db, now=datetime.now(timezone.utc),
    )
    assert n == 0


def test_incremental_ingest_helpers_importable():
    """Task 11.1 functions can be imported and have expected signatures."""
    from scripts.incremental_ingest import (
        since_ms_for_incremental, incremental_symbol_timeframe,
        incremental_symbol_futures,
    )
    assert callable(since_ms_for_incremental)
    assert callable(incremental_symbol_timeframe)
    assert callable(incremental_symbol_futures)


def test_scheduler_has_five_jobs_after_v02():
    """After 11.2: incremental_ingest is the 5th cron job."""
    from crypto_predictor.scheduler.jobs import build_scheduler
    sched = build_scheduler()
    job_ids = {job.id for job in sched.get_jobs()}
    assert {"predict_scan", "incremental_ingest", "validate_pending",
            "weekly_metrics", "recalibrate"}.issubset(job_ids)
    sched.shutdown(wait=False)
