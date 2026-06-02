"""JSON persistence for calibration maps."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

from crypto_predictor.calibration.isotonic import RegimeCalibrators


def save_calibration(calibs: RegimeCalibrators, path: Path, *,
                     fit_window: str) -> None:
    """Save fitted calibrators as JSON with knot points."""
    data = {"fit_window": fit_window, "regimes": {}}
    for regime, ir in calibs.by_regime.items():
        data["regimes"][regime] = {
            "x": ir.X_thresholds_.tolist(),
            "y": ir.y_thresholds_.tolist(),
            "increasing": True,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_calibration(path: Path) -> RegimeCalibrators:
    """Load calibrators from JSON. Returns empty object if file missing."""
    calibs = RegimeCalibrators()
    if not path.exists():
        return calibs
    data = json.loads(path.read_text(encoding="utf-8"))
    for regime, payload in data.get("regimes", {}).items():
        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        x = np.array(payload["x"])
        y = np.array(payload["y"])
        ir.fit(x, y)
        calibs.by_regime[regime] = ir
    return calibs
