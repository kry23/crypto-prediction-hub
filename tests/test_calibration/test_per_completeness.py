import json
from pathlib import Path

from crypto_predictor.calibration.per_completeness import (
    PerCompletenessCalibration,
    save_per_completeness,
    load_per_completeness,
    lookup_calibrated_probability,
)


def _make_fit(x_max: float = 0.5, y_max: float = 0.9) -> dict:
    return {
        "x": [0.0, x_max], "y": [0.4, y_max],
        "prior_alpha": 1.0, "prior_beta": 1.0, "n_per_knot": [100, 100],
    }


def test_save_and_load_roundtrip(tmp_path: Path):
    cal = PerCompletenessCalibration(
        fit_window="2026-03-27..2026-06-17",
        by_completeness={
            "full": {"BULL": _make_fit(), "CHOP": _make_fit(0.4, 0.85)},
            "degraded": {"BULL": _make_fit(0.3, 0.7)},
        },
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )
    path = tmp_path / "cal_0_3_0.json"
    save_per_completeness(cal, path)
    loaded = load_per_completeness(path)
    assert loaded.fit_window == cal.fit_window
    assert set(loaded.by_completeness.keys()) == {"full", "degraded"}
    assert set(loaded.by_completeness["full"].keys()) == {"BULL", "CHOP"}


def test_lookup_uses_completeness_specific_map():
    full_fit = _make_fit(0.5, 0.95)
    degraded_fit = _make_fit(0.5, 0.7)  # lower ceiling for degraded
    cal = PerCompletenessCalibration(
        fit_window="x",
        by_completeness={
            "full": {"BULL": full_fit},
            "degraded": {"BULL": degraded_fit},
        },
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )
    p_full = lookup_calibrated_probability(
        cal, completeness="full", regime="BULL", direction_raw=0.5,
    )
    p_degraded = lookup_calibrated_probability(
        cal, completeness="degraded", regime="BULL", direction_raw=0.5,
    )
    assert p_full > p_degraded


def test_sparse_regime_falls_back_to_full_map():
    cal = PerCompletenessCalibration(
        fit_window="x",
        by_completeness={
            "full": {"BULL": _make_fit(), "BEAR": _make_fit(0.4, 0.8)},
            "degraded": {"BULL": _make_fit()},  # BEAR absent
        },
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )
    # degraded BEAR doesn't exist -> fallback to full BEAR
    p = lookup_calibrated_probability(
        cal, completeness="degraded", regime="BEAR", direction_raw=0.2,
    )
    p_expected = lookup_calibrated_probability(
        cal, completeness="full", regime="BEAR", direction_raw=0.2,
    )
    assert p == p_expected


def test_missing_completeness_key_falls_back_to_full():
    cal = PerCompletenessCalibration(
        fit_window="x",
        by_completeness={"full": {"BULL": _make_fit()}},
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )
    # "degraded" key entirely absent -> fallback to full
    p = lookup_calibrated_probability(
        cal, completeness="degraded", regime="BULL", direction_raw=0.2,
    )
    p_full = lookup_calibrated_probability(
        cal, completeness="full", regime="BULL", direction_raw=0.2,
    )
    assert p == p_full


def test_json_schema_includes_fit_window_and_smoothing(tmp_path: Path):
    cal = PerCompletenessCalibration(
        fit_window="W",
        by_completeness={"full": {"BULL": _make_fit()}},
        smoothing={"prior_alpha": 2.0, "prior_beta": 3.0},
        extrapolation={"cap": 0.99},
    )
    path = tmp_path / "cal.json"
    save_per_completeness(cal, path)
    raw = json.loads(path.read_text())
    assert raw["fit_window"] == "W"
    assert raw["smoothing"]["prior_alpha"] == 2.0
    assert raw["extrapolation"]["cap"] == 0.99


def test_empty_by_completeness_raises_on_lookup():
    cal = PerCompletenessCalibration(
        fit_window="x", by_completeness={},
        smoothing={"prior_alpha": 1.0, "prior_beta": 1.0},
        extrapolation={"cap": 1.0},
    )
    import pytest
    with pytest.raises((KeyError, ValueError)):
        lookup_calibrated_probability(
            cal, completeness="full", regime="BULL", direction_raw=0.2,
        )


def test_load_missing_file_returns_none(tmp_path: Path):
    loaded = load_per_completeness(tmp_path / "missing.json")
    assert loaded is None
