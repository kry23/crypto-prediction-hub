"""Cron job registry — defines schedule, jobs are no-ops in Plan A."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import structlog
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.orchestrator.universe import (
    assign_mcap_ranks,
    list_active_perps,
)
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics
from crypto_predictor.validation.validator import validate_pending_predictions

log = structlog.get_logger(__name__)


def _job_predict_scan() -> None:
    """Fire the daily prediction scan (06:00 UTC)."""
    log.info("predict_scan_start")

    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    history_root = project_root / "data" / "history"
    predictions_db = project_root / "predictions.db"
    sector_map = project_root / "data" / "sector_map.yaml"
    sentiment_cache = project_root / "data" / "sentiment_cache.db"
    global_cache = project_root / "data" / "global_cache.db"
    calibration_path = project_root / "data" / "calibration_1_5_4.json"

    okx = ccxt.okx({"enableRateLimit": True})
    symbols = list_active_perps(okx)

    mcap_ranks_path = project_root / "data" / "mcap_ranks.yaml"
    if mcap_ranks_path.exists():
        mcap_map = yaml.safe_load(mcap_ranks_path.read_text(encoding="utf-8")) or {}
    else:
        mcap_map = {}
    mcap_ranks = assign_mcap_ranks(symbols, mcap_map)

    llm_client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            from anthropic import Anthropic
            llm_client = Anthropic(api_key=api_key)
        except ImportError:
            log.warning("anthropic_sdk_not_installed")

    result = run_full_scan(
        history_root=history_root,
        sentiment_cache=sentiment_cache,
        global_cache=global_cache,
        sector_map=sector_map,
        predictions_db=predictions_db,
        calibration_path=calibration_path,
        symbols=symbols,
        mcap_ranks=mcap_ranks,
        asof=datetime.now(timezone.utc),
        formula_version="v1.5",
        llm_client=llm_client,
    )

    # === Output delivery (Task 8.5) ===
    from crypto_predictor.config import load_secrets
    from crypto_predictor.output.markdown_report import render_daily_report
    from crypto_predictor.output.telegram_summary import (
        render_telegram_summary, render_high_conviction_alert,
    )
    from crypto_predictor.output.telegram_delivery import send_message
    from crypto_predictor.output.thresholds import (
        load_thresholds, classify_high_conviction,
    )

    slate = result["slate"]
    asof = datetime.now(timezone.utc)

    # Markdown report
    from crypto_predictor.validation.rolling_metrics import load_rolling_metrics_from_db
    rolling = load_rolling_metrics_from_db(predictions_db)
    report_md = render_daily_report(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
        n_scanned=len(symbols), n_skipped=result["scan"]["n_skipped"],
        rolling_metrics=rolling,
    )
    report_dir = project_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_filename = report_dir / f"predict-{asof.strftime('%Y-%m-%d-%H%M')}.md"
    report_filename.write_text(report_md, encoding="utf-8")
    log.info("daily_report_written", path=str(report_filename))

    # Telegram delivery
    secrets = load_secrets(project_root / "data" / "secrets.env")
    bot_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = secrets.get("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        summary_msg = render_telegram_summary(
            asof=asof, regime=result["scan"]["regime"], slate=slate,
            report_filename=f"reports/{report_filename.name}",
        )
        send_message(bot_token=bot_token, chat_id=chat_id, text=summary_msg)

        thresholds = load_thresholds(project_root / "data" / "thresholds.yaml")
        high_conv = classify_high_conviction(
            slate.top_long + slate.top_short, thresholds,
        )
        if high_conv:
            alert_msg = render_high_conviction_alert(high_conv[:10])
            send_message(bot_token=bot_token, chat_id=chat_id, text=alert_msg)

    log.info("predict_scan_done",
             n_predictions=result["scan"]["n_predictions"])


def _job_validate_pending() -> None:
    """Close pending predictions whose horizon has elapsed."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    n = validate_pending_predictions(
        predictions_db=project_root / "predictions.db",
        history_root=project_root / "data" / "history",
        now=datetime.now(timezone.utc),
    )
    log.info("validate_pending_done", n_closed=n)


def _job_weekly_metrics() -> None:
    """Refresh rolling metrics table."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    n = update_rolling_metrics(
        predictions_db=project_root / "predictions.db",
        now=datetime.now(timezone.utc),
    )
    log.info("weekly_metrics_done", n_rows=n)


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
