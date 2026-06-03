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

from crypto_predictor.config import load_secrets
from crypto_predictor.logging_config import configure_logging
from crypto_predictor.output.post_validation import (
    format_validation_telegram,
    lookback_window,
    summarize_recent_closures,
)
from crypto_predictor.output.telegram_delivery import send_message
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
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram summary even if secrets are set.")
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
    if n == 0 or args.no_telegram:
        return 0

    summary = summarize_recent_closures(
        db_path=args.db, since=lookback_window(now, hours=24),
    )
    log.info("post_validation_summary",
             n=summary.get("n_closed", 0),
             hit_rate=summary.get("hit_rate"),
             brier=summary.get("brier"))
    secrets = load_secrets(project_root / "data" / "secrets.env")
    token = secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat = secrets.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        msg = format_validation_telegram(summary)
        if msg:
            send_message(bot_token=token, chat_id=chat, text=msg)
            log.info("post_validation_telegram_sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
