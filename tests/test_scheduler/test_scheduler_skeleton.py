from crypto_predictor.scheduler.jobs import build_scheduler, list_registered_jobs


def test_scheduler_has_four_jobs():
    sched = build_scheduler()
    names = list_registered_jobs(sched)
    assert "predict_scan" in names
    assert "validate_pending" in names
    assert "weekly_metrics" in names
    assert "recalibrate" in names
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
