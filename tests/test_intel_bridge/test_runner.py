"""Smoke tests for scripts/run_intel_bridge.py."""
import threading
from unittest.mock import patch

from scripts.run_intel_bridge import run_until_signal


def test_runner_exits_when_stop_event_preset(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://does/not/matter")
    stop = threading.Event()
    stop.set()
    with patch("psycopg.connect"):
        rc = run_until_signal(stop_event=stop, poll_interval=1, max_ticks=1)
    assert rc in (0, 1)  # 0 = no tick happened before stop


def test_runner_returns_error_when_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rc = run_until_signal(
        stop_event=threading.Event(), poll_interval=1, max_ticks=1
    )
    assert rc == 1


def test_runner_bounded_by_max_ticks(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://does/not/matter")
    with patch("psycopg.connect"):
        rc = run_until_signal(
            stop_event=threading.Event(), poll_interval=0, max_ticks=2
        )
    assert rc == 0
