"""Configuration + secrets loader (intel-hub pattern)."""
from __future__ import annotations

from pathlib import Path


class MissingSecretError(KeyError):
    """Raised when a required secret is not present in the loaded env."""


def load_secrets(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from a dotenv-style file. Missing file → empty dict."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def require_secret(secrets: dict[str, str], name: str) -> str:
    """Return secret value or raise MissingSecretError."""
    if name not in secrets or not secrets[name]:
        raise MissingSecretError(f"required secret '{name}' is missing")
    return secrets[name]
