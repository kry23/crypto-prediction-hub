from datetime import datetime, timezone

from crypto_predictor.orchestrator.ranker import RankedSlate
from crypto_predictor.output.telegram_summary import (
    render_telegram_summary, render_high_conviction_alert,
    render_scan_start_heartbeat,
)


def test_render_telegram_summary_under_800_chars():
    slate = RankedSlate(
        top_long=[
            {"symbol": "SOL/USDT:USDT", "p_direction": 0.78, "target_value": 0.05},
            {"symbol": "AVAX/USDT:USDT", "p_direction": 0.74, "target_value": 0.048},
            {"symbol": "LINK/USDT:USDT", "p_direction": 0.73, "target_value": 0.041},
        ],
        top_short=[
            {"symbol": "ENS/USDT:USDT", "p_direction": 0.71, "target_value": -0.041},
            {"symbol": "NEAR/USDT:USDT", "p_direction": 0.69, "target_value": -0.038},
        ],
        wild_cards=[],
    )
    msg = render_telegram_summary(
        asof=datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc),
        regime="BULL",
        slate=slate,
        report_filename="reports/predict-2026-06-02-0600.md",
    )
    assert "Predictor" in msg
    assert "BULL" in msg
    assert "SOL" in msg
    assert len(msg) < 800


def test_render_high_conviction_alert_lists_candidates():
    candidates = [
        {"symbol": "SOL/USDT:USDT", "p_direction": 0.82, "target_value": 0.06,
         "rationale": "Funding ext negative."},
        {"symbol": "AVAX/USDT:USDT", "p_direction": 0.80, "target_value": 0.055,
         "rationale": "Momentum aligned."},
    ]
    msg = render_high_conviction_alert(candidates)
    assert "SOL" in msg
    assert "AVAX" in msg
    assert "High Conv" in msg or "high conv" in msg.lower()


def test_scan_start_heartbeat_shadow_one_line():
    asof = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)
    msg = render_scan_start_heartbeat(asof=asof, regime="CHOP", n_symbols=336,
                                        mode="shadow",
                                        calibration_version="1_5_4")
    assert msg.count("\n") == 0
    assert "\U0001f52c" in msg
    assert "06:00" in msg
    assert "336" in msg
    assert "CHOP" in msg
    assert "shadow" in msg.lower()


def test_scan_start_heartbeat_live_variant():
    asof = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)
    msg = render_scan_start_heartbeat(asof=asof, regime="CHOP", n_symbols=336,
                                        mode="live",
                                        calibration_version="0_3_0")
    assert "\U0001f4ca" in msg
    assert "live" in msg.lower()


def test_scan_start_heartbeat_includes_calibration_version():
    asof = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)
    msg = render_scan_start_heartbeat(asof=asof, regime="BULL", n_symbols=340,
                                        mode="live",
                                        calibration_version="0_3_0")
    assert "0_3_0" in msg
