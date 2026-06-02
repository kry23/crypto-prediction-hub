"""Alert routing thresholds — load from YAML, classify predictions."""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS = {
    "high_conv_p": 0.78,
    "high_conv_ret": 0.04,
    "calibration_drift_brier_delta": 0.05,
    "pattern_seek_min": 0.65,
    "pattern_avoid_max": 0.50,
}


def load_thresholds(path: Path) -> dict:
    if not path.exists():
        return dict(DEFAULTS)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULTS)
    merged.update(raw)
    return merged


def classify_high_conviction(predictions: list[dict],
                              thresholds: dict) -> list[dict]:
    """Return predictions that meet high-conviction criteria (excludes wild cards)."""
    p_thresh = thresholds["high_conv_p"]
    ret_thresh = thresholds["high_conv_ret"]
    return [
        p for p in predictions
        if p.get("confidence_flag") != "WILD_CARD"
        and p["p_direction"] >= p_thresh
        and abs(p["target_value"]) >= ret_thresh
    ]
