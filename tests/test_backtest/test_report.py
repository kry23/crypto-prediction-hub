from pathlib import Path

from crypto_predictor.backtest.report import render_backtest_report


def test_render_includes_overall_section(tmp_path: Path):
    report = render_backtest_report(
        title="Test backtest",
        window_label="2026-01-01..2026-05-31",
        overall={
            "hit_rate": 0.612,
            "mae": 0.0234,
            "brier": 0.218,
            "n_predictions": 1200,
        },
        per_regime={
            "BULL": {"hit_rate": 0.641, "n": 290},
            "BEAR": {"hit_rate": 0.587, "n": 420},
            "CHOP": {"hit_rate": 0.604, "n": 490},
        },
        calibration_buckets=[
            {"bucket_low": 0.5, "bucket_high": 0.6,
             "predicted_mean": 0.55, "empirical_rate": 0.512, "n": 100},
            {"bucket_low": 0.7, "bucket_high": 0.8,
             "predicted_mean": 0.75, "empirical_rate": 0.674, "n": 100},
        ],
        top_k_alpha={"long": 0.032, "short": 0.021, "combined": 0.053},
        survivorship_bias_flag=True,
    )
    assert "Test backtest" in report
    assert "Hit rate" in report
    assert "61.2%" in report
    assert "BULL" in report
    assert "calibration" in report.lower()
    assert "survivorship" in report.lower()
