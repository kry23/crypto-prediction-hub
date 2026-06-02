from unittest.mock import MagicMock, patch

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
