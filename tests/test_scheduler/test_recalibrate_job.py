from crypto_predictor.scheduler.jobs import _job_recalibrate


def test_recalibrate_job_runs_without_crash():
    """Phase 1 scaffold: just verify it doesn't crash."""
    _job_recalibrate()  # should not raise
