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

When started in production (no injected stop_event), the runner also
spawns a tiny Flask app on 127.0.0.1:8502 exposing `/health` and `/jobs`.
The Operator UI page queries `/jobs` to render the next-fire-time table.
The endpoint is bound to loopback only and never exposed externally.
"""
from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

# Project root must be on sys.path so scheduler.jobs can `from scripts.X import Y`.
# When invoked as `python scripts/run_scheduler.py`, Python only adds scripts/
# to sys.path; pytest adds the project root automatically but the runtime
# script does not. Without this line jobs.py fails at import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.scheduler.jobs import build_scheduler, list_registered_jobs

log = structlog.get_logger(__name__)


def _build_jobs_app(scheduler):
    """Build the Flask app exposing /health and /jobs for the given scheduler.

    Factored out so unit tests can construct an app against a mock scheduler
    and exercise the endpoint via Flask's test client (no live port bind).
    """
    from flask import Flask, jsonify

    app = Flask(__name__)

    @app.get("/health")
    def _health():
        return jsonify({"status": "ok"})

    @app.get("/jobs")
    def _jobs():
        out = []
        for job in scheduler.get_jobs():
            next_run = (
                job.next_run_time.isoformat() if job.next_run_time else None
            )
            out.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run,
                "trigger": str(job.trigger),
                "misfire_grace_time": job.misfire_grace_time,
                "coalesce": job.coalesce,
            })
        return jsonify({"jobs": out})

    return app


def _start_jobs_endpoint(scheduler, *, host: str = "127.0.0.1",
                          port: int = 8502) -> threading.Thread:
    """Start the Flask /jobs server in a daemon thread. Returns the thread."""
    app = _build_jobs_app(scheduler)

    def _serve():
        # debug=False / use_reloader=False so we don't fork or watch files.
        # threaded=True so the UI's polling doesn't block other requests.
        app.run(
            host=host,
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    t = threading.Thread(target=_serve, daemon=True,
                         name="scheduler-jobs-endpoint")
    t.start()
    log.info("jobs_endpoint_started", host=host, port=port)
    return t


def run_until_signal(stop_event: threading.Event | None = None) -> int:
    """Build, resume, and block until SIGTERM/SIGINT. Returns exit code.

    When ``stop_event`` is None (production path), also starts the
    /jobs Flask endpoint. When ``stop_event`` is provided (unit tests),
    the endpoint is NOT started — keeps port 8502 free for tests that
    run in parallel.
    """
    configure_logging()
    sched = build_scheduler()
    sched.resume()
    log.info("scheduler_running",
             jobs=list_registered_jobs(sched),
             timezone=str(sched.timezone))

    stop = stop_event or threading.Event()

    if stop_event is None:
        # Production-only side effects: signal handlers + HTTP endpoint.
        def _stop(signum, _frame):  # noqa: ANN001
            log.info("scheduler_shutdown_signal", signum=signum)
            stop.set()

        signal.signal(signal.SIGINT, _stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop)

        try:
            _start_jobs_endpoint(sched)
        except Exception as exc:  # pragma: no cover - defensive
            # Don't crash the scheduler if Flask fails to bind. Log and
            # carry on — the UI will gracefully show "endpoint unreachable".
            log.warning("jobs_endpoint_failed_to_start", error=str(exc))

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
