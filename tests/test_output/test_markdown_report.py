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


def test_ceiling_badge_applied_when_p_at_regime_ceiling():
    slate = RankedSlate(
        top_long=[
            {"symbol": "BERA/USDT:USDT", "p_direction": 0.9198,
             "target_value": 0.025, "composite_score": 0.023,
             "rationale": "Ceiling-hit"},
            {"symbol": "ETH/USDT:USDT", "p_direction": 0.72,
             "target_value": 0.03, "composite_score": 0.022,
             "rationale": "Below ceiling"},
        ],
        top_short=[],
        wild_cards=[
            {"symbol": "DOOD/USDT:USDT", "p_direction": 0.9198,
             "target_value": 0.022, "composite_score": 0.014,
             "rationale": "Ceiling-hit anomaly"},
        ],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc),
        regime="CHOP",
        slate=slate,
        n_scanned=340, n_skipped=0,
        rolling_metrics={},
        regime_ceilings={"CHOP": 0.9198, "BULL": 1.0},
    )
    assert "BERA/USDT:USDT | 0.92*" in md
    assert "ETH/USDT:USDT | 0.72 " in md
    assert "DOOD/USDT:USDT** P=0.92*" in md
    assert "calibration ceiling reached (0.92)" in md


def test_no_ceiling_badge_when_no_predictions_at_ceiling():
    slate = RankedSlate(
        top_long=[
            {"symbol": "ETH/USDT:USDT", "p_direction": 0.72,
             "target_value": 0.03, "composite_score": 0.022,
             "rationale": "Below ceiling"},
        ],
        top_short=[],
        wild_cards=[],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc),
        regime="CHOP", slate=slate, n_scanned=10, n_skipped=0,
        rolling_metrics={}, regime_ceilings={"CHOP": 0.9198},
    )
    assert "calibration ceiling reached" not in md
    assert "0.72*" not in md
    assert "| 0.72 |" in md


def test_render_daily_report_works_without_regime_ceilings():
    slate = RankedSlate(
        top_long=[{"symbol": "BTC/USDT:USDT", "p_direction": 0.65,
                   "target_value": 0.02, "composite_score": 0.013,
                   "rationale": ""}],
        top_short=[], wild_cards=[],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc),
        regime="BULL", slate=slate, n_scanned=1, n_skipped=0,
        rolling_metrics={},
    )
    assert "BTC/USDT:USDT" in md
    assert "0.65" in md
    assert "ceiling" not in md.lower()


def test_composite_score_rendered_as_basis_points():
    # composite_score=0.00027 -> 0.00027 * 10000 = 2.7bp
    slate = RankedSlate(
        top_long=[{"symbol": "BTC/USDT:USDT", "p_direction": 0.60,
                   "target_value": 0.0045, "composite_score": 0.00027,
                   "rationale": "Edge case low composite."}],
        top_short=[], wild_cards=[],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc),
        regime="BULL", slate=slate, n_scanned=1, n_skipped=0,
        rolling_metrics={},
    )
    assert "Composite (bp)" in md
    assert "2.7bp" in md
    assert "0.000" not in md  # old raw decimal format must be gone
