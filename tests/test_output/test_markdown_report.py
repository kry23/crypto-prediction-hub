from datetime import datetime, timezone

from crypto_predictor.orchestrator.ranker import RankedSlate
from crypto_predictor.output.markdown_report import render_daily_report


def test_render_daily_report_includes_all_sections():
    slate = RankedSlate(
        top_long=[{"symbol": "SOL/USDT:USDT", "p_direction": 0.78,
                   "target_value": 0.05, "composite_score": 0.039,
                   "rationale": "Funding negative, OI rising."}],
        top_short=[{"symbol": "ENS/USDT:USDT", "p_direction": 0.71,
                    "target_value": -0.04, "composite_score": 0.028,
                    "rationale": "Crowded longs, liq cascade."}],
        wild_cards=[{"symbol": "AGIX/USDT:USDT", "p_direction": 0.81,
                     "target_value": 0.07, "composite_score": 0.040,
                     "rationale": "OI +340% — unprecedented."}],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc),
        regime="BULL",
        slate=slate,
        n_scanned=340, n_skipped=13,
        rolling_metrics={"7d": {"hit_rate": 0.641, "n": 280, "alpha": 0.0312},
                         "30d": {"hit_rate": 0.625, "n": 1200, "alpha": 0.0242}},
    )
    assert "Crypto Predictor — Daily Report" in md
    assert "2026-06-02 06:00 UTC" in md
    assert "Regime: **BULL**" in md
    assert "SOL/USDT:USDT" in md
    assert "ENS/USDT:USDT" in md
    assert "AGIX/USDT:USDT" in md
    assert "Wild Cards" in md
    assert "Validation Track Record" in md
