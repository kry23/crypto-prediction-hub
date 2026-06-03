from pathlib import Path

import pytest

from crypto_predictor.config import load_secrets, MissingSecretError


def test_load_secrets_reads_env_file(tmp_path: Path):
    env = tmp_path / "secrets.env"
    env.write_text("FOO=bar\nBAZ=qux\n")
    secrets = load_secrets(env)
    assert secrets["FOO"] == "bar"
    assert secrets["BAZ"] == "qux"


def test_load_secrets_strips_quotes(tmp_path: Path):
    env = tmp_path / "secrets.env"
    env.write_text('TOKEN="abc123"\n')
    assert load_secrets(env)["TOKEN"] == "abc123"


def test_load_secrets_missing_file_returns_empty(tmp_path: Path):
    assert load_secrets(tmp_path / "missing.env") == {}


def test_require_secret_raises_when_absent():
    from crypto_predictor.config import require_secret
    with pytest.raises(MissingSecretError):
        require_secret({}, "TELEGRAM_BOT_TOKEN")
