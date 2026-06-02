from unittest.mock import patch

from crypto_predictor.scheduler.jobs import (
    _job_validate_pending, _job_weekly_metrics,
)


@patch("crypto_predictor.scheduler.jobs.validate_pending_predictions")
def test_validate_pending_calls_validator(mock_validate):
    mock_validate.return_value = 5
    _job_validate_pending()
    mock_validate.assert_called_once()


@patch("crypto_predictor.scheduler.jobs.update_rolling_metrics")
def test_weekly_metrics_calls_aggregator(mock_update):
    mock_update.return_value = 12
    _job_weekly_metrics()
    mock_update.assert_called_once()
