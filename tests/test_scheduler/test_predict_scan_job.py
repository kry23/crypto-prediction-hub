from unittest.mock import MagicMock, patch

from crypto_predictor.config.scheduler_config import SchedulerConfig
from crypto_predictor.scheduler.jobs import _job_predict_scan


@patch("crypto_predictor.scheduler.jobs.run_full_scan")
def test_predict_scan_job_calls_orchestrator(mock_run):
    fake_slate = MagicMock(top_long=[], top_short=[], wild_cards=[])
    mock_run.return_value = {"scan": {"n_predictions": 5, "n_skipped": 0, "regime": "BULL"},
                              "slate": fake_slate}
    # Mock ccxt to avoid network calls
    with patch("crypto_predictor.scheduler.jobs.ccxt") as mock_ccxt:
        mock_okx = MagicMock()
        mock_okx.load_markets.return_value = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "swap": True,
                              "settle": "USDT", "active": True},
        }
        mock_ccxt.okx.return_value = mock_okx
        _job_predict_scan()
    mock_run.assert_called_once()


def test_predict_scan_loads_config_and_threads_mode():
    """End-to-end: config drives mode + calibration_version into run_full_scan."""
    fake_slate = MagicMock(top_long=[], top_short=[], wild_cards=[])
    with patch("crypto_predictor.scheduler.jobs.load_scheduler_config") as mock_config, \
         patch("crypto_predictor.scheduler.jobs.run_full_scan") as mock_scan, \
         patch("crypto_predictor.scheduler.jobs.list_active_perps") as mock_perps, \
         patch("crypto_predictor.scheduler.jobs.send_message") as mock_send, \
         patch("crypto_predictor.scheduler.jobs.ccxt"):
        mock_config.return_value = SchedulerConfig(
            mode="shadow", calibration_version="1_5_4",
            tilt_weights_version="phase_1_5",
        )
        mock_perps.return_value = ["BTC/USDT:USDT"]
        mock_scan.return_value = {
            "scan": {"regime": "CHOP", "n_predictions": 1, "n_skipped": 0},
            "slate": fake_slate,
        }
        _job_predict_scan()
        assert mock_scan.called
        kwargs = mock_scan.call_args.kwargs
        assert kwargs.get("mode") == "shadow"
        assert kwargs.get("calibration_version") == "1_5_4"


def test_predict_scan_skips_telegram_when_shadow_silent_flag_set():
    """shadow_skip_telegram=True should skip ALL Telegram calls in the scan."""
    fake_slate = MagicMock(top_long=[], top_short=[], wild_cards=[])
    with patch("crypto_predictor.scheduler.jobs.load_scheduler_config") as mock_config, \
         patch("crypto_predictor.scheduler.jobs.run_full_scan") as mock_scan, \
         patch("crypto_predictor.scheduler.jobs.list_active_perps") as mock_perps, \
         patch("crypto_predictor.scheduler.jobs.send_message") as mock_send, \
         patch("crypto_predictor.scheduler.jobs.load_secrets") as mock_secrets, \
         patch("crypto_predictor.scheduler.jobs.ccxt"):
        mock_config.return_value = SchedulerConfig(
            mode="shadow", calibration_version="1_5_4",
            tilt_weights_version="phase_1_5", shadow_skip_telegram=True,
        )
        mock_perps.return_value = ["BTC/USDT:USDT"]
        mock_scan.return_value = {
            "scan": {"regime": "CHOP", "n_predictions": 1, "n_skipped": 0},
            "slate": fake_slate,
        }
        mock_secrets.return_value = {"TELEGRAM_BOT_TOKEN": "tok",
                                      "TELEGRAM_CHAT_ID": "chat"}
        _job_predict_scan()
        # No telegram sent when shadow_skip_telegram=True
        assert not mock_send.called
