from unittest.mock import patch

from crypto_predictor.config.scheduler_config import SchedulerConfig
from crypto_predictor.scheduler.jobs import (
    _job_validate_pending, _job_weekly_metrics,
)


_LIVE_CONFIG = SchedulerConfig(
    mode="live", calibration_version="1_5_4",
    tilt_weights_version="phase_1_5",
)
_SHADOW_CONFIG = SchedulerConfig(
    mode="shadow", calibration_version="1_5_4",
    tilt_weights_version="phase_1_5",
)
_SHADOW_SILENT_CONFIG = SchedulerConfig(
    mode="shadow", calibration_version="1_5_4",
    tilt_weights_version="phase_1_5", shadow_skip_telegram=True,
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


@patch("crypto_predictor.scheduler.jobs.load_scheduler_config",
        return_value=_LIVE_CONFIG)
@patch("crypto_predictor.scheduler.jobs.send_message")
@patch("crypto_predictor.scheduler.jobs.load_secrets")
@patch("crypto_predictor.scheduler.jobs.summarize_recent_closures")
@patch("crypto_predictor.scheduler.jobs.validate_pending_predictions")
def test_validate_pending_sends_telegram_on_close(
    mock_validate, mock_summary, mock_secrets, mock_send, mock_config,
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


def test_validate_pending_uses_shadow_telegram_variant_when_mode_shadow():
    """Shadow mode threads mode='shadow' kwarg into format_validation_telegram."""
    with patch("crypto_predictor.scheduler.jobs.load_scheduler_config") as mock_config, \
         patch("crypto_predictor.scheduler.jobs.validate_pending_predictions") as mock_v, \
         patch("crypto_predictor.scheduler.jobs.summarize_recent_closures") as mock_sum, \
         patch("crypto_predictor.scheduler.jobs.format_validation_telegram") as mock_fmt, \
         patch("crypto_predictor.scheduler.jobs.send_message") as mock_send, \
         patch("crypto_predictor.scheduler.jobs.load_secrets") as mock_secrets:
        mock_config.return_value = _SHADOW_CONFIG
        mock_v.return_value = 5
        mock_sum.return_value = {
            "n_closed": 5, "n_correct": 2, "hit_rate": 0.4, "brier": 0.30,
            "by_flag": {}, "by_regime": {}, "by_direction": {},
        }
        mock_fmt.return_value = "\U0001f52c Shadow validation\nClosed: 5"
        mock_secrets.return_value = {"TELEGRAM_BOT_TOKEN": "tok",
                                      "TELEGRAM_CHAT_ID": "chat"}
        _job_validate_pending()
        assert mock_fmt.called
        kwargs = mock_fmt.call_args.kwargs
        assert kwargs.get("mode") == "shadow"
        mock_send.assert_called_once()


def test_validate_pending_skips_telegram_when_shadow_silent_flag_set():
    """shadow_skip_telegram=True should skip ALL Telegram calls."""
    with patch("crypto_predictor.scheduler.jobs.load_scheduler_config") as mock_config, \
         patch("crypto_predictor.scheduler.jobs.validate_pending_predictions") as mock_v, \
         patch("crypto_predictor.scheduler.jobs.summarize_recent_closures") as mock_sum, \
         patch("crypto_predictor.scheduler.jobs.format_validation_telegram") as mock_fmt, \
         patch("crypto_predictor.scheduler.jobs.send_message") as mock_send, \
         patch("crypto_predictor.scheduler.jobs.load_secrets") as mock_secrets:
        mock_config.return_value = _SHADOW_SILENT_CONFIG
        mock_v.return_value = 5
        mock_sum.return_value = {
            "n_closed": 5, "n_correct": 2, "hit_rate": 0.4, "brier": 0.30,
            "by_flag": {}, "by_regime": {}, "by_direction": {},
        }
        mock_secrets.return_value = {"TELEGRAM_BOT_TOKEN": "tok",
                                      "TELEGRAM_CHAT_ID": "chat"}
        _job_validate_pending()
        # Telegram should never be invoked
        mock_send.assert_not_called()
        mock_fmt.assert_not_called()
