"""Long-running poller for whale + news data. systemd entry point.

Wired into ``deploy/systemd/crypto-predictor-intel-bridge.service``. Stops
gracefully on SIGINT / SIGTERM. The default poll interval is 15 minutes
(``INTEL_BRIDGE_INTERVAL_SECONDS`` overrides).

For v1.0 the fetchers are stubs (return []) — the bridge wires up the
loop, DB pool, logging, and shutdown plumbing so Day-14 can drop in real
fetcher implementations without touching the runner.
"""
from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path

import structlog

# Match scripts/run_scheduler.py: project root on sys.path so
# `from crypto_predictor.X import Y` resolves when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.intel_bridge.fetchers import (  # noqa: E402
    StubNewsFetcher,
    StubWhaleFetcher,
)
from crypto_predictor.intel_bridge.poller import poll_news, poll_whales  # noqa: E402
from crypto_predictor.logging_config import configure_logging  # noqa: E402

log = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("INTEL_BRIDGE_INTERVAL_SECONDS", "900"))
# default 15 minutes


def run_until_signal(
    *,
    stop_event: threading.Event | None = None,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    max_ticks: int | None = None,
) -> int:
    """Main loop. ``stop_event`` for tests; ``max_ticks`` bounds the loop in tests.

    Returns 0 on clean shutdown, 1 when DATABASE_URL is missing.
    """
    configure_logging()
    whale = StubWhaleFetcher()
    news = StubNewsFetcher()

    stop = stop_event or threading.Event()
    if stop_event is None:
        def _stop(signum, _frame):  # noqa: ANN001
            log.info("intel_bridge_shutdown_signal", signum=signum)
            stop.set()

        signal.signal(signal.SIGINT, _stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop)

    # Lazy import psycopg only when needed; keeps the module importable
    # (and unit-testable) without psycopg installed.
    import psycopg  # noqa: F401

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("intel_bridge_no_database_url")
        return 1

    tick_count = 0
    while not stop.is_set():
        try:
            with psycopg.connect(db_url) as conn:
                n_whales = poll_whales(conn, whale)
                n_news = poll_news(conn, news)
            log.info("intel_bridge_tick", whales=n_whales, news=n_news)
        except Exception as exc:  # pragma: no cover - exercised via mocks
            log.exception("intel_bridge_tick_failed", error=str(exc))

        tick_count += 1
        if max_ticks is not None and tick_count >= max_ticks:
            break
        stop.wait(timeout=poll_interval)

    log.info("intel_bridge_shutdown_complete", ticks=tick_count)
    return 0


def main() -> int:
    return run_until_signal()


if __name__ == "__main__":
    sys.exit(main())
