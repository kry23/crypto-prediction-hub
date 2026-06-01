# tests/test_logging_config.py
import json

import structlog

from crypto_predictor.logging_config import configure_logging


def test_configure_logging_emits_json(capsys):
    configure_logging(level="INFO")
    log = structlog.get_logger("crypto_predictor.test")
    log.info("hello", foo="bar")
    captured = capsys.readouterr()
    line = captured.out.strip().split("\n")[-1] if captured.out else captured.err.strip().split("\n")[-1]
    data = json.loads(line)
    assert data["event"] == "hello"
    assert data["level"] == "info"
    assert data["foo"] == "bar"
