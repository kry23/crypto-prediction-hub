"""Manually trigger validate_pending — closes mature predictions on demand.

The scheduler runs `_job_validate_pending` daily at 06:30 UTC. Predictions
created mid-day (e.g., from a manual /predict-scan) only close on the *next*
06:30 UTC after their T+24h maturity, so a 11:30 UTC cohort waits ~43 hours
end-to-end. This CLI lets the user (or the autonomous monitoring loop)
close them as soon as they're actually mature.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.validation.validator import validate_pending_predictions

log = structlog.get_logger(__name__)


def main() -> int:
    configure_logging()
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[1],
    ))
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path,
                        default=project_root / "predictions.db")
    parser.add_argument("--history-root", type=Path,
                        default=project_root / "data" / "history")
    args = parser.parse_args()

    if not args.db.exists():
        log.error("db_missing", path=str(args.db))
        return 1

    now = datetime.now(timezone.utc)
    log.info("validate_pending_start", now=now.isoformat())
    n = validate_pending_predictions(
        predictions_db=args.db,
        history_root=args.history_root,
        now=now,
    )
    log.info("validate_pending_done", closed=n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
