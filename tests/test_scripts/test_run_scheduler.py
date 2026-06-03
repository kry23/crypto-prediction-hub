# tests/test_scripts/test_run_scheduler.py
"""Smoke tests for the foreground scheduler runner."""
import threading
import time
from unittest.mock import MagicMock, patch

from scripts.run_scheduler import run_until_signal


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
