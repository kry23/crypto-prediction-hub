"""Cron job registry — defines schedule, jobs are no-ops in Plan A."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import httpx
import structlog
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from crypto_predictor.calibration.drift import DriftStatus, detect_drift
from crypto_predictor.config import load_secrets
from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.orchestrator.universe import (
    assign_mcap_ranks,
    list_active_perps,
)
from crypto_predictor.output.post_validation import (
    format_validation_telegram,
    lookback_window,
    summarize_recent_closures,
)
from crypto_predictor.output.telegram_delivery import send_message
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics
from crypto_predictor.validation.validator import validate_pending_predictions
from scripts.backup_databases import DEFAULT_BACKUP_DIR, DEFAULT_KEEP, backup_all
from scripts.incremental_ingest import (
    incremental_symbol_futures,
    incremental_symbol_timeframe,
)

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
    symbols = list_active_perps(
        okx, blacklist_path=project_root / "data" / "equity_blacklist.yaml",
    )

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

    # === Cache population (v0.2) ===
    from crypto_predictor.config import load_secrets
    from crypto_predictor.sentiment.newsapi_fetcher import (
        fetch_articles_for_coin, sentiment_from_articles,
    )
    from crypto_predictor.sentiment.cache_writer import write_sentiment_for_symbol
    from crypto_predictor.global_ctx.fetcher import (
        compute_trend_pct, fetch_dominance_snapshot,
        read_sector_history, write_global_for_asof,
    )
    import httpx as _httpx

    asof_iso = datetime.now(timezone.utc).isoformat()
    newsapi_key = (load_secrets(project_root / "data" / "secrets.env")
                   .get("NEWSAPI_API_KEY", ""))
    if newsapi_key:
        http = _httpx.Client(timeout=20.0)
        # Top 30 mcap coins by rank
        top_symbols = sorted(
            [(s, r) for s, r in mcap_ranks.items() if r is not None],
            key=lambda x: x[1],
        )[:30]
        for sym, _rank in top_symbols:
            base = sym.split("/")[0].lower()
            try:
                articles = fetch_articles_for_coin(
                    http_client=http, api_key=newsapi_key,
                    coin=base, hours_back=24,
                )
                score = sentiment_from_articles(articles)
                write_sentiment_for_symbol(
                    db=sentiment_cache, symbol=sym, timestamp=asof_iso,
                    news_sent_24h=score, social_sent_24h=0.0,
                    sent_velocity=0.0, news_volume_z=float(len(articles)),
                )
            except Exception as exc:
                log.warning("sentiment_fetch_failed",
                            symbol=sym, error=str(exc))
        http.close()

    # Global context (BTC + ETH dom; 7d trends from cached history)
    try:
        gh = _httpx.Client(timeout=20.0)
        dom = fetch_dominance_snapshot(http_client=gh)
        gh.close()
        btc_dom = dom["btc"]
        eth_dom = dom["eth"]
        btc_dom_trend_7d = compute_trend_pct(
            read_sector_history(global_cache, "sector_btc", lookback_days=7)
        )
        eth_dom_trend_7d = compute_trend_pct(
            read_sector_history(global_cache, "sector_eth", lookback_days=7)
        )
        write_global_for_asof(
            db=global_cache, timestamp=asof_iso,
            btc_dom_trend_7d=btc_dom_trend_7d,
            eth_btc_trend_7d=eth_dom_trend_7d,
            total_mcap_z=0.0,
            sector_btc=btc_dom, sector_eth=eth_dom,
            sector_defi=0.0, sector_l1=0.0,
        )
    except Exception as exc:
        log.warning("global_fetch_failed", error=str(exc))

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
    from crypto_predictor.calibration.persistence import ceilings_from_calibration
    from crypto_predictor.validation.rolling_metrics import load_rolling_metrics_from_db
    rolling = load_rolling_metrics_from_db(predictions_db)
    regime_ceilings = ceilings_from_calibration(calibration_path)
    report_md = render_daily_report(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
        n_scanned=len(symbols), n_skipped=result["scan"]["n_skipped"],
        rolling_metrics=rolling,
        regime_ceilings=regime_ceilings,
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
    """Close pending predictions whose horizon has elapsed. Telegrams on close."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    now = datetime.now(timezone.utc)
    n = validate_pending_predictions(
        predictions_db=project_root / "predictions.db",
        history_root=project_root / "data" / "history",
        now=now,
    )
    log.info("validate_pending_done", n_closed=n)
    if n == 0:
        return

    summary = summarize_recent_closures(
        db_path=project_root / "predictions.db",
        since=lookback_window(now, hours=24),
    )
    if summary.get("n_closed", 0) == 0:
        return
    log.info("post_validation_summary",
             n=summary["n_closed"], hit_rate=summary.get("hit_rate"),
             brier=summary.get("brier"))

    secrets = load_secrets(project_root / "data" / "secrets.env")
    token = secrets.get("TELEGRAM_BOT_TOKEN", "")
    chat = secrets.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        return
    msg = format_validation_telegram(summary)
    if msg:
        send_message(bot_token=token, chat_id=chat, text=msg)


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
    """Drift check (Phase 1 + v0.2) — alerts via Telegram on drift."""
    log.info("recalibrate_job_start")
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    # Compute current 7d Brier from predictions table
    import sqlite3
    db = project_root / "predictions.db"
    if not db.exists():
        log.info("recalibrate_job_done", reason="no predictions.db")
        return
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT p_direction, status FROM predictions "
            "WHERE status IN ('correct','incorrect') "
            "AND validated_at >= datetime('now', '-7 days')"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        log.info("recalibrate_job_done", reason="no closed predictions in 7d")
        return
    # Brier = mean of (p - label)^2
    labels = [1 if r[1] == "correct" else 0 for r in rows]
    probs = [r[0] for r in rows]
    brier = sum((p - l) ** 2 for p, l in zip(probs, labels)) / len(rows)

    status = detect_drift(current_brier=brier,
                          backtest_brier=0.226, delta=0.05)
    log.info("recalibrate_drift_check",
             current_brier=brier, status=str(status))

    if status == DriftStatus.DRIFT:
        secrets = load_secrets(project_root / "data" / "secrets.env")
        token = secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat = secrets.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
            msg = (f"⚠ CALIBRATION DRIFT DETECTED\n"
                   f"Current 7d Brier: {brier:.3f}\n"
                   f"Backtest baseline: 0.226\n"
                   f"Delta: +{brier - 0.226:.3f}\n"
                   f"Action: manually run recalibration script or "
                   f"trust degraded predictions cautiously.")
            send_message(bot_token=token, chat_id=chat, text=msg)


def _job_incremental_ingest() -> None:
    """Refresh OHLCV + futures data since last ingest (06:15 UTC)."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    root = project_root / "data" / "history"
    root.mkdir(parents=True, exist_ok=True)
    okx = ccxt.okx({"enableRateLimit": True})
    http = httpx.Client(timeout=30.0)
    symbols = list_active_perps(
        okx, blacklist_path=project_root / "data" / "equity_blacklist.yaml",
    )
    log.info("incremental_ingest_start", n_symbols=len(symbols))
    total = 0
    for sym in symbols:
        try:
            for tf in ["15m", "1h", "4h", "1d"]:
                total += incremental_symbol_timeframe(
                    client=okx, root=root, symbol=sym, timeframe=tf,
                    fallback_days=30,
                )
            incremental_symbol_futures(
                ccxt_client=okx, http_client=http, root=root,
                symbol=sym, fallback_days=30,
            )
        except Exception as exc:
            log.warning("ingest_symbol_failed", symbol=sym, error=str(exc))
    log.info("incremental_ingest_done", total_new_bars=total)


def _job_backup_databases() -> None:
    """Snapshot predictions.db + caches to ~/.crypto-predictor-backups (06:45 UTC)."""
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[3],
    ))
    log.info("backup_job_start")
    results = backup_all(source_root=project_root,
                          backup_dir=DEFAULT_BACKUP_DIR, keep=DEFAULT_KEEP)
    log.info("backup_job_done",
             dbs=sum(1 for v in results.values() if v is not None))


def build_scheduler() -> BackgroundScheduler:
    """Build scheduler with all four Phase-1 jobs registered (no-ops until later plans)."""
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_job_predict_scan,
                  CronTrigger(hour=6, minute=0), id="predict_scan", replace_existing=True)
    sched.add_job(_job_incremental_ingest,
                  CronTrigger(hour=6, minute=15), id="incremental_ingest",
                  replace_existing=True)
    sched.add_job(_job_validate_pending,
                  CronTrigger(hour=6, minute=30), id="validate_pending", replace_existing=True)
    sched.add_job(_job_backup_databases,
                  CronTrigger(hour=6, minute=45), id="backup_databases",
                  replace_existing=True)
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
