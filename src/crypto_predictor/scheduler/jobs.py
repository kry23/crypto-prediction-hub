"""Cron job registry — defines schedule, jobs are no-ops in Plan A."""
from __future__ import annotations

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = structlog.get_logger(__name__)


def _job_predict_scan() -> None:
    log.info("predict_scan job fired (no-op in Plan A)")


def _job_validate_pending() -> None:
    log.info("validate_pending job fired (no-op in Plan A)")


def _job_weekly_metrics() -> None:
    log.info("weekly_metrics job fired (no-op in Plan A)")


def _job_recalibrate() -> None:
    log.info("recalibrate job fired (no-op in Plan A)")


def build_scheduler() -> BackgroundScheduler:
    """Build scheduler with all four Phase-1 jobs registered (no-ops until later plans)."""
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_job_predict_scan,
                  CronTrigger(hour=6, minute=0), id="predict_scan", replace_existing=True)
    sched.add_job(_job_validate_pending,
                  CronTrigger(hour=6, minute=30), id="validate_pending", replace_existing=True)
    sched.add_job(_job_weekly_metrics,
                  CronTrigger(day_of_week="sun", hour=7, minute=0), id="weekly_metrics",
                  replace_existing=True)
    sched.add_job(_job_recalibrate,
                  CronTrigger(day=1, hour=7, minute=0), id="recalibrate",
                  replace_existing=True)
    sched.start(paused=True)
    return sched


def list_registered_jobs(sched: BackgroundScheduler) -> list[str]:
    return [job.id for job in sched.get_jobs()]
