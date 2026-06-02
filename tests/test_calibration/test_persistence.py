from pathlib import Path

import numpy as np

from crypto_predictor.calibration.isotonic import fit_calibration, predict_probability
from crypto_predictor.calibration.persistence import save_calibration, load_calibration


def test_save_load_roundtrip(tmp_path: Path):
    np.random.seed(0)
    rows = []
    for _ in range(100):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    path = tmp_path / "calibration_map.json"
    save_calibration(calibs, path, fit_window="2026-01-01..2026-03-31")
    loaded = load_calibration(path)
    assert loaded.has("BULL")
    for raw in [-0.5, 0.0, 0.5]:
        p_orig = predict_probability(calibs, raw_score=raw, regime="BULL")
        p_load = predict_probability(loaded, raw_score=raw, regime="BULL")
        assert abs(p_orig - p_load) < 1e-6


def test_load_missing_file_returns_empty(tmp_path: Path):
    loaded = load_calibration(tmp_path / "nope.json")
    assert not loaded.has("BULL")
