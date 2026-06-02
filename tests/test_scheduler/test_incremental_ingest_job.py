from unittest.mock import patch, MagicMock

from crypto_predictor.scheduler.jobs import (
    _job_incremental_ingest, build_scheduler,
)


@patch("crypto_predictor.scheduler.jobs.list_active_perps")
@patch("crypto_predictor.scheduler.jobs.incremental_symbol_timeframe")
@patch("crypto_predictor.scheduler.jobs.incremental_symbol_futures")
def test_incremental_ingest_job_calls_fetchers(
    mock_futures, mock_tf, mock_list_perps,
):
    mock_list_perps.return_value = ["BTC/USDT:USDT"]
    mock_tf.return_value = 5
    mock_futures.return_value = {"funding": 1, "oi": 1, "ls_ratio": 1, "liq": 1}
    with patch("crypto_predictor.scheduler.jobs.ccxt") as mock_ccxt, \
         patch("crypto_predictor.scheduler.jobs.httpx") as mock_httpx:
        mock_ccxt.okx.return_value = MagicMock()
        mock_httpx.Client.return_value = MagicMock()
        _job_incremental_ingest()
    assert mock_tf.call_count >= 1


def test_scheduler_includes_incremental_ingest_job():
    sched = build_scheduler()
    job_ids = [job.id for job in sched.get_jobs()]
    assert "incremental_ingest" in job_ids
    sched.shutdown(wait=False)
