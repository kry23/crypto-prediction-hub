"""Unit tests for ``crypto_predictor.ui.systemd_helpers``.

These verify the dev-mode (no systemd) fallbacks and that the HTTP
client gracefully returns an empty list when the scheduler /jobs
endpoint isn't reachable. We mock ``shutil.which`` to simulate
both environments without depending on the host OS.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# --- systemd_available ----------------------------------------------------

@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_systemd_available_returns_true_when_systemctl_present(mock_which):
    mock_which.return_value = "/bin/systemctl"
    from crypto_predictor.ui.systemd_helpers import systemd_available
    assert systemd_available() is True


@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_systemd_available_returns_false_on_windows(mock_which):
    mock_which.return_value = None
    from crypto_predictor.ui.systemd_helpers import systemd_available
    assert systemd_available() is False


# --- scheduler_status -----------------------------------------------------

@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_scheduler_status_no_systemd_returns_placeholder(mock_which):
    mock_which.return_value = None
    from crypto_predictor.ui.systemd_helpers import scheduler_status
    s = scheduler_status()
    assert s["active"] is False
    assert "no-systemd" in s["state"]
    assert s["uptime"] is None


@patch("crypto_predictor.ui.systemd_helpers.subprocess.run")
@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_scheduler_status_parses_active_state(mock_which, mock_run):
    mock_which.return_value = "/bin/systemctl"
    # is-active result, then show ActiveEnterTimestamp result.
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="active\n", stderr=""),
        MagicMock(
            returncode=0,
            stdout="Mon 2026-06-05 12:00:00 UTC\n",
            stderr="",
        ),
    ]
    from crypto_predictor.ui.systemd_helpers import scheduler_status
    s = scheduler_status("crypto-predictor-scheduler")
    assert s["active"] is True
    assert s["state"] == "active"
    assert s["uptime"] == "Mon 2026-06-05 12:00:00 UTC"


# --- next_jobs ------------------------------------------------------------

def test_next_jobs_returns_empty_when_endpoint_unreachable():
    """Hitting a bogus port should return [] rather than raise."""
    from crypto_predictor.ui.systemd_helpers import next_jobs
    assert next_jobs(base_url="http://127.0.0.1:1") == []


@patch("crypto_predictor.ui.systemd_helpers.httpx.Client")
def test_next_jobs_parses_endpoint_response(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "jobs": [
            {"id": "predict_scan", "next_run": "2026-06-06T06:00:00+00:00"},
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response
    from crypto_predictor.ui.systemd_helpers import next_jobs
    out = next_jobs()
    assert len(out) == 1
    assert out[0]["id"] == "predict_scan"


@patch("crypto_predictor.ui.systemd_helpers.httpx.Client")
def test_next_jobs_returns_empty_on_malformed_payload(mock_client_cls):
    """Non-dict payload should fall back to [] without crashing."""
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.json.return_value = ["not", "a", "dict"]
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response
    from crypto_predictor.ui.systemd_helpers import next_jobs
    assert next_jobs() == []


# --- restart_service ------------------------------------------------------

@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_restart_service_no_systemd_returns_failure(mock_which):
    mock_which.return_value = None
    from crypto_predictor.ui.systemd_helpers import restart_service
    rc, out = restart_service("crypto-predictor-scheduler")
    assert rc == 1
    assert "systemd not available" in out


@patch("crypto_predictor.ui.systemd_helpers.subprocess.run")
@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_restart_service_returns_subprocess_rc(mock_which, mock_run):
    mock_which.return_value = "/bin/systemctl"
    mock_run.return_value = MagicMock(
        returncode=0, stdout="", stderr="",
    )
    from crypto_predictor.ui.systemd_helpers import restart_service
    rc, _out = restart_service("crypto-predictor-scheduler")
    assert rc == 0
    # Verify sudo systemctl restart was invoked
    assert mock_run.call_args.args[0][:3] == [
        "sudo", "systemctl", "restart",
    ]


# --- tail_journal ---------------------------------------------------------

@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_tail_journal_no_systemd_returns_placeholder(mock_which):
    mock_which.return_value = None
    from crypto_predictor.ui.systemd_helpers import tail_journal
    out = tail_journal("any-unit")
    assert "local dev" in out


@patch("crypto_predictor.ui.systemd_helpers.subprocess.run")
@patch("crypto_predictor.ui.systemd_helpers.shutil.which")
def test_tail_journal_returns_subprocess_stdout(mock_which, mock_run):
    mock_which.return_value = "/bin/systemctl"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"MESSAGE":"hello"}\n',
        stderr="",
    )
    from crypto_predictor.ui.systemd_helpers import tail_journal
    out = tail_journal("crypto-predictor-scheduler", lines=10)
    assert "hello" in out


# --- trigger_script -------------------------------------------------------

def test_trigger_script_returns_exit_code_and_output(tmp_path):
    """Run a real subprocess against an echo-style script."""
    script = tmp_path / "echo.py"
    script.write_text("print('hello-from-trigger')\n")
    from crypto_predictor.ui.systemd_helpers import trigger_script
    rc, out = trigger_script(str(script), timeout=30)
    assert rc == 0
    assert "hello-from-trigger" in out


def test_trigger_script_returns_nonzero_on_failure(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(7)\n")
    from crypto_predictor.ui.systemd_helpers import trigger_script
    rc, _out = trigger_script(str(script), timeout=30)
    assert rc == 7
