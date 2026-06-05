"""Helpers to talk to systemd and to the scheduler's /jobs endpoint.

Designed to work on Hetzner (Linux + systemd + journalctl) AND on the
Windows dev machine (returns mocked/empty data where systemd isn't
available). Detection is via ``shutil.which('systemctl')``.

Every public function in this module degrades gracefully when systemd
is absent — callers (the Operator Streamlit page) can render without
crashing in either environment.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import httpx


def systemd_available() -> bool:
    """Return True when ``systemctl`` resolves on PATH (Linux prod box)."""
    return shutil.which("systemctl") is not None


def _systemctl_show_property(unit: str, prop: str) -> str | None:
    """Run ``systemctl show <unit> -p <prop> --value`` and return the value.

    Returns None on any failure (unit missing, permission denied, etc.).
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "-p", prop, "--value"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def scheduler_status(
    unit: str = "crypto-predictor-scheduler",
) -> dict:
    """Return scheduler service state.

    Shape: ``{'active': bool, 'state': str, 'uptime': str | None}``.

    When systemd is unavailable returns a placeholder dict so the page
    layer can still render. ``state`` is the raw output of
    ``systemctl is-active`` (``active``, ``inactive``, ``failed``, ...).
    """
    if not systemd_available():
        return {
            "active": False,
            "state": "no-systemd-on-this-host",
            "uptime": None,
        }
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {"active": False, "state": f"error: {exc}", "uptime": None}
    state = (result.stdout or "").strip() or "unknown"
    active = state == "active"
    uptime = _systemctl_show_property(unit, "ActiveEnterTimestamp")
    return {"active": active, "state": state, "uptime": uptime}


def next_jobs(*, base_url: str = "http://127.0.0.1:8502") -> list[dict]:
    """Query the scheduler's ``/jobs`` HTTP endpoint.

    Returns the parsed list of job dicts on success, or an empty list
    when the scheduler isn't running / endpoint isn't reachable. Never
    raises — callers can treat an empty list as "no data available".
    """
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{base_url}/jobs")
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def restart_service(name: str) -> tuple[int, str]:
    """Restart a systemd unit via ``sudo systemctl restart``.

    Returns ``(returncode, combined_output)``. When systemd is absent
    returns ``(1, "<placeholder>")`` so the UI can show a friendly
    message instead of crashing in dev mode.
    """
    if not systemd_available():
        return (1, "systemd not available on this host (dev mode?)")
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", name],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return (124, f"timeout restarting {name}")
    except (subprocess.SubprocessError, OSError) as exc:
        return (1, f"error restarting {name}: {exc}")
    return (result.returncode, (result.stdout or "") + (result.stderr or ""))


def tail_journal(unit: str, *, lines: int = 100) -> str:
    """Tail recent systemd journal lines for ``unit`` as JSON-lines text.

    Uses ``journalctl -u <unit> -n <lines> --no-pager --output=json``.
    Returns a placeholder string when systemd is unavailable so the
    page can render in dev mode.
    """
    if not systemd_available():
        return "[systemd not available — local dev mode]"
    try:
        result = subprocess.run(
            [
                "journalctl", "-u", unit, "-n", str(lines),
                "--no-pager", "--output=json",
            ],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return f"[timeout reading journal for {unit}]"
    except (subprocess.SubprocessError, OSError) as exc:
        return f"[error reading journal: {exc}]"
    return result.stdout or ""


def trigger_script(script_path: str, *args: str,
                    timeout: int = 600) -> tuple[int, str]:
    """Run a Python script from ``scripts/`` via the project venv.

    Captured stdout+stderr are concatenated and returned with the exit
    code. Times out at ``timeout`` seconds (returns rc=124 on timeout,
    matching coreutils convention).
    """
    cmd = [sys.executable, script_path, *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (124, f"timeout after {timeout}s")
    except (subprocess.SubprocessError, OSError) as exc:
        return (1, f"error running {script_path}: {exc}")
    return (result.returncode, (result.stdout or "") + (result.stderr or ""))
