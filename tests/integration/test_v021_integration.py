"""End-to-end importability + safe-default smoke for the v0.2.1 batch."""
from pathlib import Path


def test_v021_modules_importable():
    """All v0.2.1 modules can be imported without side effects."""
    from crypto_predictor.config.scheduler_config import (
        SchedulerConfig, load_scheduler_config,
    )
    from crypto_predictor.orchestrator.feature_completeness import (
        detect_feature_completeness,
    )
    from crypto_predictor.output.telegram_summary import (
        render_scan_start_heartbeat,
    )
    from crypto_predictor.output.post_validation import (
        format_validation_telegram,
    )
    from crypto_predictor.output.markdown_report import (
        render_daily_report,
    )
    from scripts.migrate_v021_mode import migrate_to_v021
    assert callable(load_scheduler_config)
    assert callable(detect_feature_completeness)
    assert callable(render_scan_start_heartbeat)
    assert callable(format_validation_telegram)
    assert callable(render_daily_report)
    assert callable(migrate_to_v021)


def test_v021_safe_default_is_shadow(tmp_path: Path):
    """Missing scheduler_config.yaml -> shadow default (never live)."""
    from crypto_predictor.config.scheduler_config import load_scheduler_config
    config = load_scheduler_config(tmp_path / "missing.yaml")
    assert config.mode == "shadow"


def test_v021_scan_start_heartbeat_smoke():
    """Heartbeat renders the expected one-line format."""
    from datetime import datetime, timezone
    from crypto_predictor.output.telegram_summary import (
        render_scan_start_heartbeat,
    )
    msg = render_scan_start_heartbeat(
        asof=datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc),
        regime="detecting", n_symbols=336,
        mode="shadow", calibration_version="1_5_4",
    )
    assert "scan start" in msg
    assert "336" in msg
    assert msg.count("\n") == 0
