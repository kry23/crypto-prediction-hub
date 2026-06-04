"""End-to-end: per-completeness calibration honors feature_completeness.

Covers the Task 10 activation switch: when ``data/calibration_*.json`` is in
the v0.3 ``by_completeness`` schema, the runtime must use
``lookup_calibrated_probability`` with the scan-level
``feature_completeness`` so that ``"full"`` and ``"degraded"`` scans on the
same raw direction land on different calibrated probabilities. When the file
is in the legacy ``regimes`` schema (Plan B / v1.5) or absent, the legacy
``predict_probability`` path must still be honored.
"""
from __future__ import annotations

import json

from crypto_predictor.calibration.per_completeness import (
    PerCompletenessCalibration, lookup_calibrated_probability,
)
from crypto_predictor.calibration.persistence import (
    detect_calibration_format,
)
from crypto_predictor.scoring.direction import calibrate_direction


def _full_vs_degraded_cal() -> PerCompletenessCalibration:
    full_fit = {
        "x": [0.0, 0.5], "y": [0.5, 0.95],
        "prior_alpha": 1.0, "prior_beta": 1.0, "n_per_knot": [100, 100],
    }
    degraded_fit = {
        "x": [0.0, 0.5], "y": [0.5, 0.65],
        "prior_alpha": 1.0, "prior_beta": 1.0, "n_per_knot": [100, 100],
    }
    return PerCompletenessCalibration(
        fit_window="x",
        by_completeness={
            "full": {"BULL": full_fit},
            "degraded": {"BULL": degraded_fit},
        },
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )


def test_full_vs_degraded_produces_different_p():
    cal = _full_vs_degraded_cal()
    p_full = lookup_calibrated_probability(
        cal, completeness="full", regime="BULL", direction_raw=0.4,
    )
    p_deg = lookup_calibrated_probability(
        cal, completeness="degraded", regime="BULL", direction_raw=0.4,
    )
    assert p_full > p_deg


def test_detect_calibration_format_recognizes_per_completeness(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "fit_window": "x",
        "by_completeness": {"full": {"BULL": {"x": [0.0], "y": [0.5]}}},
        "smoothing": {}, "extrapolation": {},
    }))
    assert detect_calibration_format(path) == "per_completeness"


def test_detect_calibration_format_recognizes_legacy(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "fit_window": "x",
        "regimes": {"BULL": {"x": [0.0], "y": [0.5], "increasing": True}},
    }))
    assert detect_calibration_format(path) == "legacy"


def test_detect_calibration_format_missing_file(tmp_path):
    assert detect_calibration_format(tmp_path / "absent.json") == "missing"


def test_detect_calibration_format_unrecognised_json_is_missing(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"unrelated": True}))
    assert detect_calibration_format(path) == "missing"


def test_detect_calibration_format_invalid_json_is_missing(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text("not valid json")
    assert detect_calibration_format(path) == "missing"


# ---------- calibrate_direction dispatcher ----------

def test_calibrate_direction_per_completeness_path(tmp_path):
    cal_path = tmp_path / "calibration_0_3_0.json"
    cal_path.write_text(json.dumps({
        "fit_window": "x",
        "by_completeness": {
            "full": {"BULL": {
                "x": [0.0, 0.5], "y": [0.5, 0.95],
                "prior_alpha": 1.0, "prior_beta": 1.0,
                "n_per_knot": [100, 100],
            }},
            "degraded": {"BULL": {
                "x": [0.0, 0.5], "y": [0.5, 0.65],
                "prior_alpha": 1.0, "prior_beta": 1.0,
                "n_per_knot": [100, 100],
            }},
        },
        "smoothing": {"prior_alpha": 1.0, "prior_beta": 1.0},
        "extrapolation": {"cap": 1.0},
    }))

    p_full = calibrate_direction(
        calibration_path=cal_path, direction_raw=0.4,
        regime="BULL", feature_completeness="full",
    )
    p_deg = calibrate_direction(
        calibration_path=cal_path, direction_raw=0.4,
        regime="BULL", feature_completeness="degraded",
    )
    assert p_full > p_deg
    # Sanity: outputs are valid probabilities.
    assert 0.0 <= p_deg <= p_full <= 1.0


def test_calibrate_direction_legacy_path_uses_predict_probability(tmp_path):
    """Legacy JSON (Plan B / v1.5) must continue to work unchanged.

    Asserts the dispatcher returns the same value the legacy
    ``predict_probability`` would.
    """
    from crypto_predictor.calibration.isotonic import predict_probability
    from crypto_predictor.calibration.persistence import load_calibration

    cal_path = tmp_path / "calibration_1_5_4.json"
    cal_path.write_text(json.dumps({
        "fit_window": "2026-01-01..2026-03-31",
        "regimes": {"BULL": {
            "x": [-1.0, 0.0, 1.0],
            "y": [0.1, 0.5, 0.9],
            "increasing": True,
        }},
    }))

    calibs = load_calibration(cal_path)
    expected = predict_probability(
        calibs, raw_score=0.3, regime="BULL",
    )
    got = calibrate_direction(
        calibration_path=cal_path, direction_raw=0.3,
        regime="BULL", feature_completeness="full",
    )
    assert abs(got - expected) < 1e-9


def test_calibrate_direction_missing_file_returns_neutral(tmp_path):
    p = calibrate_direction(
        calibration_path=tmp_path / "absent.json",
        direction_raw=0.7, regime="BULL", feature_completeness="full",
    )
    assert p == 0.5


def test_calibrate_direction_none_path_returns_neutral():
    p = calibrate_direction(
        calibration_path=None, direction_raw=0.7,
        regime="BULL", feature_completeness="full",
    )
    assert p == 0.5
