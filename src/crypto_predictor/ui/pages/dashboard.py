"""Dashboard page — today's slate, regime, ceiling badge, annotations.

Spec: docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md §4.1.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.db import get_conn
from crypto_predictor.ui.queries import todays_slate

email = require_auth()
st.title("📊 Dashboard")
st.caption("Auto-refresh: 60 s")


@st.cache_data(ttl=60)
def _load(mode: str) -> dict:
    """Cache the slate for 60 s so the auto-refresh is cheap."""
    with get_conn() as conn:
        return todays_slate(conn, mode=mode)


mode = st.session_state.get("ui_mode_filter", "shadow")
data = _load(mode)

# --- Header metric strip ---------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("Regime", data["regime"])
m2.metric("Mode", mode)
m3.metric("Calibration", data["calibration_version"])
m4.metric("Ceiling-hit", data["n_ceiling_hit"])

st.caption(
    f"{data['n_predictions']} predictions · "
    f"{data['n_wild_cards']} wild cards · "
    f"next scan: {data['next_scan_dt'].strftime('%H:%M UTC')}"
)
st.divider()


def _render_prediction_table(rows: list[dict], *, prob_label: str) -> None:
    """Shared renderer for the long/short/wild-card tables."""
    df = pd.DataFrame(rows)
    df["composite_bp"] = df["composite_score"] * 10000
    display = df[["symbol", "p_direction", "target_value", "composite_bp"]].rename(
        columns={
            "p_direction": prob_label,
            "target_value": "Exp.ret",
            "composite_bp": "Composite (bp)",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)


# --- Top long --------------------------------------------------------------
st.subheader("📈 Top long")
if data["top_long"]:
    _render_prediction_table(data["top_long"], prob_label="P↑")
else:
    st.info("No long predictions today.")

# --- Top short -------------------------------------------------------------
st.subheader("📉 Top short")
if data["top_short"]:
    _render_prediction_table(data["top_short"], prob_label="P↓")
else:
    st.info("No short predictions today.")

# --- Wild cards ------------------------------------------------------------
st.subheader("🃏 Wild cards")
if data["wild_cards"]:
    _render_prediction_table(data["wild_cards"], prob_label="P")
else:
    st.info("No wild cards today.")

# --- Active manual annotations --------------------------------------------
st.subheader("📌 Active manual annotations")
if data["active_annotations"]:
    df_ann = pd.DataFrame(data["active_annotations"])
    st.dataframe(df_ann, use_container_width=True, hide_index=True)
else:
    st.caption("No open positions. The annotations form ships in v1.2.")
