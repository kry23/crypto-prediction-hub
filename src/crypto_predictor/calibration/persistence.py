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


def detect_calibration_format(path: Path) -> str:
    """Inspect a calibration JSON and report which schema it uses.

    Returns:
        ``"per_completeness"`` — v0.3 schema with ``by_completeness`` key.
        ``"legacy"``           — Plan B / v1.5 schema with ``regimes`` key.
        ``"missing"``          — file absent or unparseable.

    Pure read; no object construction. Used by the runtime to dispatch
    between :func:`load_per_completeness` and :func:`load_calibration`.
    """
    if not path.exists():
        return "missing"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "missing"
    if "by_completeness" in raw:
        return "per_completeness"
    if "regimes" in raw:
        return "legacy"
    return "missing"


def ceilings_from_calibration(path: Path) -> dict[str, float]:
    """Return {regime: max(y)} for each regime in the calibration JSON.

    Used by the daily report to mark predictions whose p_direction is saturated
    against the isotonic map's upper bound, where ranking reduces to magnitude.
    Returns {} if the file is missing.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        regime: max(payload["y"])
        for regime, payload in data.get("regimes", {}).items()
        if payload.get("y")
    }
