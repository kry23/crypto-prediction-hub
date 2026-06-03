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


@patch("crypto_predictor.scheduler.jobs.send_message")
@patch("crypto_predictor.scheduler.jobs.load_secrets")
@patch("crypto_predictor.scheduler.jobs.summarize_recent_closures")
@patch("crypto_predictor.scheduler.jobs.validate_pending_predictions")
def test_validate_pending_sends_telegram_on_close(
    mock_validate, mock_summary, mock_secrets, mock_send,
):
    mock_validate.return_value = 5
    mock_summary.return_value = {
        "n_closed": 5, "n_correct": 4, "hit_rate": 0.8, "brier": 0.18,
        "by_flag": {}, "by_regime": {}, "by_direction": {},
    }
    mock_secrets.return_value = {"TELEGRAM_BOT_TOKEN": "tok",
                                  "TELEGRAM_CHAT_ID": "chat"}
    _job_validate_pending()
    mock_summary.assert_called_once()
    mock_send.assert_called_once()
    _kwargs = mock_send.call_args.kwargs
    assert _kwargs["bot_token"] == "tok"
    assert _kwargs["chat_id"] == "chat"
    assert "Validation cycle complete" in _kwargs["text"]


@patch("crypto_predictor.scheduler.jobs.send_message")
@patch("crypto_predictor.scheduler.jobs.summarize_recent_closures")
@patch("crypto_predictor.scheduler.jobs.validate_pending_predictions")
def test_validate_pending_skips_telegram_when_no_close(
    mock_validate, mock_summary, mock_send,
):
    mock_validate.return_value = 0
    _job_validate_pending()
    mock_summary.assert_not_called()
    mock_send.assert_not_called()
