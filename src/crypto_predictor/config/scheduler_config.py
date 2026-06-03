"""Scheduler runtime configuration loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

VALID_MODES = {"shadow", "live"}


@dataclass(frozen=True)
class SchedulerConfig:
    mode: Literal["shadow", "live"]
    calibration_version: str
    tilt_weights_version: str
    telegram_chat_id_override: str | None = None
    shadow_skip_telegram: bool = False


def _safe_default() -> SchedulerConfig:
    return SchedulerConfig(
        mode="shadow",
        calibration_version="1_5_4",
        tilt_weights_version="phase_1_5",
    )


def load_scheduler_config(path: Path) -> SchedulerConfig:
    """Load from YAML. Missing file -> safe shadow default.

    Raises ValueError on unknown mode; yaml.YAMLError on malformed file.
    """
    if not path.exists():
        return _safe_default()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mode = data.get("mode", "shadow")
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode: {mode!r} (allowed: {VALID_MODES})")
    return SchedulerConfig(
        mode=mode,
        calibration_version=str(data.get("calibration_version", "1_5_4")),
        tilt_weights_version=str(data.get("tilt_weights_version",
                                          "phase_1_5")),
        telegram_chat_id_override=data.get("telegram_chat_id_override"),
        shadow_skip_telegram=bool(data.get("shadow_skip_telegram", False)),
    )
