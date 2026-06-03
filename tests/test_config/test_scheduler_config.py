from pathlib import Path

import pytest

from crypto_predictor.config.scheduler_config import (
    SchedulerConfig,
    load_scheduler_config,
)


def test_missing_file_returns_safe_shadow_default(tmp_path: Path):
    config = load_scheduler_config(tmp_path / "does_not_exist.yaml")
    assert config.mode == "shadow"
    assert config.calibration_version == "1_5_4"
    assert config.tilt_weights_version == "phase_1_5"
    assert config.shadow_skip_telegram is False
    assert config.telegram_chat_id_override is None


def test_valid_yaml_parses_into_typed_dataclass(tmp_path: Path):
    path = tmp_path / "scheduler_config.yaml"
    path.write_text(
        "mode: live\n"
        "calibration_version: '0_3_0'\n"
        "tilt_weights_version: '0_3_0'\n"
        "shadow_skip_telegram: true\n"
        "telegram_chat_id_override: '999'\n",
        encoding="utf-8",
    )
    config = load_scheduler_config(path)
    assert config.mode == "live"
    assert config.calibration_version == "0_3_0"
    assert config.tilt_weights_version == "0_3_0"
    assert config.shadow_skip_telegram is True
    assert config.telegram_chat_id_override == "999"


def test_unknown_mode_raises(tmp_path: Path):
    path = tmp_path / "scheduler_config.yaml"
    path.write_text("mode: paused\ncalibration_version: '1_5_4'\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="mode"):
        load_scheduler_config(path)


def test_malformed_yaml_raises(tmp_path: Path):
    path = tmp_path / "scheduler_config.yaml"
    path.write_text("mode: shadow\n  invalid indent\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_scheduler_config(path)
