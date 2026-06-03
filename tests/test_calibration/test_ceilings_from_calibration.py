# tests/test_calibration/test_ceilings_from_calibration.py
import json
from pathlib import Path

from crypto_predictor.calibration.persistence import ceilings_from_calibration


def test_ceilings_from_calibration_returns_max_y_per_regime(tmp_path: Path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "fit_window": "test",
        "regimes": {
            "BULL": {"x": [0.0, 0.5], "y": [0.3, 1.0], "increasing": True},
            "CHOP": {"x": [0.0, 0.3], "y": [0.4, 0.9198], "increasing": True},
        },
    }))
    out = ceilings_from_calibration(path)
    assert out == {"BULL": 1.0, "CHOP": 0.9198}


def test_ceilings_from_calibration_handles_missing_file(tmp_path: Path):
    path = tmp_path / "does_not_exist.json"
    assert ceilings_from_calibration(path) == {}


def test_ceilings_from_calibration_skips_empty_y(tmp_path: Path):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "regimes": {
            "BULL": {"x": [], "y": []},
            "CHOP": {"x": [0.0], "y": [0.5]},
        },
    }))
    assert ceilings_from_calibration(path) == {"CHOP": 0.5}
