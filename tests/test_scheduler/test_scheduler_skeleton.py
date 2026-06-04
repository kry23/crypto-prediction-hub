from crypto_predictor.scheduler.jobs import build_scheduler, list_registered_jobs


def test_scheduler_has_four_jobs():
    sched = build_scheduler()
    names = list_registered_jobs(sched)
    assert "predict_scan" in names
    assert "validate_pending" in names
    assert "weekly_metrics" in names
    assert "recalibrate" in names
    assert "incremental_ingest" in names
    assert "backup_databases" in names
    sched.shutdown(wait=False)


def test_backup_databases_job_at_0645_utc():
    from apscheduler.triggers.cron import CronTrigger
    sched = build_scheduler()
    by_name = {job.id: job for job in sched.get_jobs()}
    trig = by_name["backup_databases"].trigger
    assert isinstance(trig, CronTrigger)
    fields = {f.name: str(f) for f in trig.fields}
    assert fields["hour"] == "6"
    assert fields["minute"] == "45"
    sched.shutdown(wait=False)


def test_scheduler_jobs_have_correct_cron():
    from apscheduler.triggers.cron import CronTrigger
    sched = build_scheduler()
    by_name = {job.id: job for job in sched.get_jobs()}
    # predict_scan: daily 06:00 UTC
    trig = by_name["predict_scan"].trigger
    assert isinstance(trig, CronTrigger)
    fields = {f.name: str(f) for f in trig.fields}
    assert fields["hour"] == "6"
    assert fields["minute"] == "0"
    sched.shutdown(wait=False)


def test_all_triggers_use_utc_timezone():
    """Every CronTrigger must have its timezone explicitly set to UTC.
    Inheriting from BackgroundScheduler proved unreliable on Windows in
    practice (2026-06-04 launch fired at host-local time)."""
    sched = build_scheduler()
    for job in sched.get_jobs():
        tz_name = str(job.trigger.timezone)
        assert tz_name == "UTC", f"{job.id} trigger timezone is {tz_name!r}"
    sched.shutdown(wait=False)


def test_all_jobs_have_misfire_grace_time():
    """Default misfire_grace_time of 1s caused the 2026-06-04 predict_scan
    to be silently dropped when APScheduler woke 3.88s late. Every job
    must allow at least 60 s tolerance."""
    sched = build_scheduler()
    for job in sched.get_jobs():
        assert job.misfire_grace_time is not None, f"{job.id} has no grace"
        assert job.misfire_grace_time >= 60, (
            f"{job.id} grace too tight: {job.misfire_grace_time}s"
        )
    sched.shutdown(wait=False)


def test_all_jobs_coalesce_backlog():
    """If multiple firings stack up (paused scheduler, sleep, etc.) we
    want exactly one make-up run, not a flurry."""
    sched = build_scheduler()
    for job in sched.get_jobs():
        assert job.coalesce is True, f"{job.id} coalesce={job.coalesce}"
    sched.shutdown(wait=False)
