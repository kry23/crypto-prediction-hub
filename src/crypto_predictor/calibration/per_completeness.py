"""Per-(completeness, regime) calibration storage + lookup with fallback."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from crypto_predictor.calibration.v03_pipeline import apply_calibrated_lookup


@dataclass
class PerCompletenessCalibration:
    fit_window: str
    by_completeness: dict[str, dict[str, dict]]  # {completeness: {regime: fit_dict}}
    smoothing: dict
    extrapolation: dict


def save_per_completeness(cal: PerCompletenessCalibration, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cal), indent=2), encoding="utf-8")


def load_per_completeness(path: Path) -> PerCompletenessCalibration | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PerCompletenessCalibration(**raw)


def lookup_calibrated_probability(
    cal: PerCompletenessCalibration, *, completeness: str, regime: str,
    direction_raw: float,
) -> float:
    """Look up calibrated p with completeness/regime fallback to full/regime."""
    full_map = cal.by_completeness.get("full", {})
    completeness_map = cal.by_completeness.get(completeness, {})
    fit = completeness_map.get(regime) or full_map.get(regime)
    if fit is None:
        raise KeyError(
            f"No calibration map for completeness={completeness} regime={regime} "
            f"and no fallback in 'full'"
        )
    return apply_calibrated_lookup(fit, direction_raw=direction_raw)
