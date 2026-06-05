# tests/test_scripts/test_run_scheduler.py
"""Smoke tests for the foreground scheduler runner."""
import threading
import time
from unittest.mock import MagicMock, patch

from scripts.run_scheduler import _build_jobs_app, run_until_signal


@patch("scripts.run_scheduler.build_scheduler")
def test_runner_resumes_and_shuts_down(mock_build):
    sched = MagicMock()
    sched.timezone = "UTC"
    sched.get_jobs.return_value = []
    mock_build.return_value = sched

    stop_event = threading.Event()
    threading.Timer(0.2, stop_event.set).start()
    rc = run_until_signal(stop_event=stop_event)

    assert rc == 0
    sched.resume.assert_called_once()
    sched.shutdown.assert_called_once_with(wait=True)


@patch("scripts.run_scheduler.build_scheduler")
def test_runner_exits_quickly_when_event_preset(mock_build):
    sched = MagicMock()
    sched.timezone = "UTC"
    sched.get_jobs.return_value = []
    mock_build.return_value = sched

    stop_event = threading.Event()
    stop_event.set()  # pre-set: should not block
    t0 = time.monotonic()
    rc = run_until_signal(stop_event=stop_event)
    elapsed = time.monotonic() - t0

    assert rc == 0
    assert elapsed < 5, f"runner blocked unexpectedly ({elapsed:.2f}s)"


def test_jobs_endpoint_returns_registered_jobs_as_json():
    """``/jobs`` should return the scheduler's registered jobs as JSON.

    Uses Flask's test client against ``_build_jobs_app`` so we don't have
    to bind a live port. Also verifies the empty-scheduler case and the
    /health probe.
    """
    sched = MagicMock()

    job = MagicMock()
    job.id = "predict_scan"
    job.name = "predict_scan"
    job.next_run_time = None
    job.trigger = "cron[hour=6]"
    job.misfire_grace_time = 300
    job.coalesce = True
    sched.get_jobs.return_value = [job]

    app = _build_jobs_app(sched)
    client = app.test_client()

    r = client.get("/jobs")
    assert r.status_code == 200
    payload = r.get_json()
    assert "jobs" in payload
    assert len(payload["jobs"]) == 1
    j = payload["jobs"][0]
    assert j["id"] == "predict_scan"
    assert j["next_run"] is None
    assert j["misfire_grace_time"] == 300
    assert j["coalesce"] is True

    h = client.get("/health")
    assert h.status_code == 200
    assert h.get_json() == {"status": "ok"}


def test_jobs_endpoint_handles_empty_scheduler():
    sched = MagicMock()
    sched.get_jobs.return_value = []
    app = _build_jobs_app(sched)
    client = app.test_client()
    r = client.get("/jobs")
    assert r.status_code == 200
    assert r.get_json() == {"jobs": []}


@patch("scripts.run_scheduler.build_scheduler")
def test_runner_does_not_start_endpoint_when_stop_event_injected(mock_build):
    """When ``stop_event`` is passed (unit test path), the /jobs Flask
    endpoint must NOT be started — keeps port 8502 free."""
    sched = MagicMock()
    sched.timezone = "UTC"
    sched.get_jobs.return_value = []
    mock_build.return_value = sched

    stop_event = threading.Event()
    stop_event.set()

    with patch(
        "scripts.run_scheduler._start_jobs_endpoint"
    ) as mock_start:
        rc = run_until_signal(stop_event=stop_event)

    assert rc == 0
    mock_start.assert_not_called()
