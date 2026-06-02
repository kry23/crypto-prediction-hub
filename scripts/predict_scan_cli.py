"""On-demand wrapper around the predict_scan scheduler job."""
from __future__ import annotations

import sys

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.scheduler.jobs import _job_predict_scan


def main() -> int:
    configure_logging()
    _job_predict_scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
