"""Operator page — scheduler control + config flip + manual triggers.

Spec: docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md §4.3.

Renders six sections:
  1. Scheduler status (systemctl is-active + uptime)
  2. Next job firings (queried from scheduler's /jobs endpoint)
  3. Restart button (sudo systemctl restart, with confirmation)
  4. Active config form (edits data/scheduler_config.yaml, then restarts)
  5. Manual triggers (one button per CLI script in scripts/)
  6. Recent logs (journalctl tail)

Designed to render on both Hetzner (full systemd) and the Windows dev
machine (gracefully degraded — systemctl is absent so most cards show
"n/a" but the page never crashes).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from crypto_predictor.config.scheduler_config import load_scheduler_config
from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.systemd_helpers import (
    next_jobs,
    restart_service,
    scheduler_status,
    systemd_available,
    tail_journal,
    trigger_script,
)

email = require_auth()
st.title("Operator")
st.caption(f"Authenticated user: `{email}`")

# Project root: this file lives at
# src/crypto_predictor/ui/pages/operator.py — four parents up = project root.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = PROJECT_ROOT / "data" / "scheduler_config.yaml"
SCHEDULER_UNIT = "crypto-predictor-scheduler"

# ---------------------------------------------------------------------------
# 1. Scheduler status card
# ---------------------------------------------------------------------------
st.subheader("Scheduler status")
status = scheduler_status(SCHEDULER_UNIT)
cols = st.columns(4)
cols[0].metric("State", status.get("state", "unknown"))
cols[1].metric("systemd", "available" if systemd_available() else "n/a")
cols[2].metric("Active", "yes" if status.get("active") else "no")
uptime = status.get("uptime")
if uptime:
    cols[3].caption(f"Since: {uptime}")
else:
    cols[3].caption("Uptime: n/a")

# ---------------------------------------------------------------------------
# 2. Next job firings
# ---------------------------------------------------------------------------
st.subheader("Next jobs")
jobs = next_jobs()
if jobs:
    st.dataframe(jobs, use_container_width=True, hide_index=True)
else:
    st.caption(
        "Cannot reach scheduler /jobs endpoint. Either the scheduler "
        "isn't running, or it lives on a different host."
    )

# ---------------------------------------------------------------------------
# 3. Restart button (confirmation gated)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Restart scheduler")
confirm = st.text_input(
    "Type RESTART to confirm, then press the button:",
    key="restart_confirm",
)
if st.button("Restart scheduler", type="secondary"):
    if confirm == "RESTART":
        rc, out = restart_service(SCHEDULER_UNIT)
        if rc == 0:
            st.success("Scheduler restarted.")
        else:
            st.error(f"Restart failed (rc={rc}):\n{out}")
    else:
        st.warning("Type RESTART in the box above first.")

# ---------------------------------------------------------------------------
# 4. Active config form
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Active config")
try:
    config = load_scheduler_config(CONFIG_PATH)
except Exception as exc:
    st.error(f"Failed to load scheduler config: {exc}")
    st.stop()

with st.form("config_form"):
    mode = st.selectbox(
        "mode",
        options=["shadow", "live"],
        index=0 if config.mode == "shadow" else 1,
    )
    cal_v = st.text_input(
        "calibration_version", value=config.calibration_version,
    )
    tilt_v = st.text_input(
        "tilt_weights_version", value=config.tilt_weights_version,
    )
    silent = st.checkbox(
        "shadow_skip_telegram", value=config.shadow_skip_telegram,
    )
    submitted = st.form_submit_button("Save + restart")
    if submitted:
        new_yaml = {
            "mode": mode,
            "calibration_version": cal_v,
            "tilt_weights_version": tilt_v,
            "shadow_skip_telegram": silent,
        }
        # Preserve optional override if it was set in the on-disk file
        # (we don't expose it in the form, but we shouldn't blow it away).
        if config.telegram_chat_id_override is not None:
            new_yaml["telegram_chat_id_override"] = (
                config.telegram_chat_id_override
            )
        try:
            CONFIG_PATH.write_text(
                yaml.safe_dump(new_yaml, sort_keys=False),
                encoding="utf-8",
            )
            st.success(f"Config saved to {CONFIG_PATH}.")
        except OSError as exc:
            st.error(f"Failed to write config: {exc}")
        else:
            rc, out = restart_service(SCHEDULER_UNIT)
            if rc == 0:
                st.success("Scheduler restarted.")
            else:
                st.error(f"Restart failed (rc={rc}):\n{out}")

# ---------------------------------------------------------------------------
# 5. Manual triggers
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Manual triggers")

_MANUAL_BUTTONS = [
    ("predict_scan", "scripts/predict_scan_cli.py"),
    ("validate_pending", "scripts/validate_pending_cli.py"),
    ("shadow_status", "scripts/shadow_status.py"),
    ("ship_criteria_check", "scripts/ship_criteria_check.py"),
]
for label, rel_path in _MANUAL_BUTTONS:
    if st.button(f"Run {label}", key=f"manual_{label}"):
        script_abs = str(PROJECT_ROOT / rel_path)
        with st.spinner(f"Running {rel_path}..."):
            rc, out = trigger_script(script_abs)
        st.code(out or "(no output)", language=None)
        if rc != 0:
            st.warning(f"Exit code {rc}")
        else:
            st.success(f"{label} completed (rc=0)")

# ---------------------------------------------------------------------------
# 6. Recent logs
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Recent logs")
log_unit = st.selectbox(
    "Unit",
    options=[
        "crypto-predictor-scheduler",
        "crypto-predictor-ui",
        "crypto-predictor-intel-bridge",
    ],
    index=0,
)
logs = tail_journal(log_unit, lines=100)
# Cap rendered output so a giant journal doesn't blow up the page.
display = logs[:50_000] if logs else "(empty)"
st.code(display, language="json")
