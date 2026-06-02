"""Per-regime isotonic regression mapping direction_raw → P(↑)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression


@dataclass
class RegimeCalibrators:
    by_regime: dict[str, IsotonicRegression] = field(default_factory=dict)

    def has(self, regime: str) -> bool:
        return regime in self.by_regime

    def get(self, regime: str) -> IsotonicRegression | None:
        return self.by_regime.get(regime)


def fit_calibration(samples: list[tuple[float, int, str]]) -> RegimeCalibrators:
    """Fit one IsotonicRegression per regime."""
    by_regime: dict[str, list[tuple[float, int]]] = {}
    for raw, label, regime in samples:
        by_regime.setdefault(regime, []).append((float(raw), int(label)))

    calibrators = RegimeCalibrators()
    for regime, rows in by_regime.items():
        if len(rows) < 5:
            continue
        X = np.array([r[0] for r in rows]).reshape(-1, 1)
        y = np.array([r[1] for r in rows])
        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        ir.fit(X.ravel(), y)
        calibrators.by_regime[regime] = ir
    return calibrators


def predict_probability(calibs: RegimeCalibrators, *,
                        raw_score: float, regime: str) -> float:
    """Predict P(label=1) given raw score and regime. Default 0.5 if regime unknown."""
    ir = calibs.get(regime)
    if ir is None:
        return 0.5
    p = float(ir.predict([raw_score])[0])
    return max(0.0, min(1.0, p))
