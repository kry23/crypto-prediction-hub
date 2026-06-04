"""On-demand wrapper around the predict_scan scheduler job."""
from __future__ import annotations

import sys
from pathlib import Path

# Project root onto sys.path so jobs.py can `from scripts.backup_databases import ...`.
# Same reason as in run_scheduler.py: Python only puts the script's dir on sys.path,
# pytest adds project root automatically but runtime scripts don't.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.scheduler.jobs import _job_predict_scan


def main() -> int:
    configure_logging()
    _job_predict_scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
