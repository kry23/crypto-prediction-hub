"""Foreground scheduler runner — keeps the cron jobs firing.

`build_scheduler()` returns the registered jobs in a paused state for safe
unit testing. This script flips it to `resume()` and blocks the process so
APScheduler's threads stay alive.

Usage in production (PowerShell):

    python scripts\\run_scheduler.py

Run under a process supervisor (Windows Task Scheduler "at logon", or `nssm`,
or a plain `Start-Process` keeping a hidden window). Logs go to stdout in
structured JSON; redirect to a file as needed.

Stop with Ctrl-C or `SIGTERM`. Cleanup is graceful — the current job (if
any) finishes before the scheduler shuts down.
"""
from __future__ import annotations

import signal
import sys
import threading

import structlog

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.scheduler.jobs import build_scheduler, list_registered_jobs

log = structlog.get_logger(__name__)


def run_until_signal(stop_event: threading.Event | None = None) -> int:
    """Build, resume, and block until SIGTERM/SIGINT. Returns exit code."""
    configure_logging()
    sched = build_scheduler()
    sched.resume()
    log.info("scheduler_running",
             jobs=list_registered_jobs(sched),
             timezone=str(sched.timezone))

    stop = stop_event or threading.Event()

    def _stop(signum, _frame):  # noqa: ANN001
        log.info("scheduler_shutdown_signal", signum=signum)
        stop.set()

    if stop_event is None:
        signal.signal(signal.SIGINT, _stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop)

    try:
        while not stop.is_set():
            stop.wait(timeout=60)
    finally:
        sched.shutdown(wait=True)
        log.info("scheduler_shutdown_complete")
    return 0


def main() -> int:
    return run_until_signal()


if __name__ == "__main__":
    sys.exit(main())
