"""Track Record page — rolling KPIs + calibration plot + ship criteria.

Spec ref: docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md §4.2.

This is the screen the v0.3 dormant phase wraps around — the user checks it
daily to see the shadow hit-rate trending toward 62.5% so they know when
Day-14 is ripe to flip ``mode=live``. The calibration scatter plot is the
single most useful visual: each dot is a p-bucket, position relative to the
y=x diagonal tells you instantly whether the model is over- or under-
confident at that bucket.
"""
from __future__ import annotations

import subprocess

import pandas as pd
import plotly.express as px
import streamlit as st

from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.db import get_conn
from crypto_predictor.ui.queries import (
    by_regime_and_flag,
    daily_hit_rates,
    per_bucket_calibration,
    rolling_kpis,
)

# v0.3 shadow baselines — see spec §4.2 + scripts/ship_criteria_check.py.
_HIT_RATE_BASELINE = 0.625
_BRIER_BASELINE = 0.226

email = require_auth()
st.title("📈 Track record")

# Window + mode selectors.
c1, c2 = st.columns(2)
window = c1.selectbox(
    "Window", options=[7, 30, 90], index=0,
    format_func=lambda d: f"{d}d",
)
mode = c2.selectbox(
    "Mode", options=["shadow", "live", "all"], index=0,
)

# Map "all" -> None so the query layer knows to skip the filter.
mode_filter = None if mode == "all" else mode


@st.cache_data(ttl=300)  # 5-minute cache
def _load(window: int, mode_filter: str | None) -> dict:
    with get_conn() as conn:
        return {
            "kpis": rolling_kpis(
                conn, window_days=window,
                mode=mode_filter or "shadow",
            ),
            "calibration": per_bucket_calibration(
                conn, window_days=window,
                mode=mode_filter or "shadow",
            ),
            "trend": daily_hit_rates(
                conn, window_days=max(14, window),
                mode=mode_filter or "shadow",
            ),
            "breakdown": by_regime_and_flag(
                conn, window_days=window,
                mode=mode_filter or "shadow",
            ),
        }


data = _load(window, mode_filter)
kpis = data["kpis"]

# --- KPI strip -------------------------------------------------------------
st.divider()
m1, m2, m3, m4, m5 = st.columns(5)
hit_rate_delta = kpis["hit_rate"] - _HIT_RATE_BASELINE
brier_delta = kpis["brier"] - _BRIER_BASELINE
m1.metric(
    "Hit rate",
    f"{kpis['hit_rate'] * 100:.1f}%",
    delta=f"{hit_rate_delta * 100:+.1f}pp vs 62.5% baseline",
)
m2.metric(
    "Brier",
    f"{kpis['brier']:.3f}",
    delta=f"{brier_delta:+.3f} vs 0.226",
    delta_color="inverse",  # lower Brier = better
)
m3.metric("Closed", kpis["n_closed"])
m4.metric("Pending", kpis["n_pending"])
m5.metric("Expired", kpis["n_expired"])
st.divider()

# --- Hit-rate trend line chart --------------------------------------------
st.subheader("Hit rate trend")
if data["trend"]:
    trend_df = pd.DataFrame(data["trend"])
    fig = px.line(
        trend_df, x="date", y="hit_rate",
        markers=True, range_y=[0, 1],
    )
    fig.add_hline(
        y=_HIT_RATE_BASELINE,
        line_dash="dash",
        annotation_text="62.5% baseline",
    )
    fig.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough closed predictions yet.")

# --- Calibration scatter (predicted vs realized) --------------------------
st.subheader("Calibration scatter — predicted vs realized")
if data["calibration"]:
    cal_df = pd.DataFrame(data["calibration"])
    fig = px.scatter(
        cal_df, x="expected", y="realized", size="n",
        color="n", hover_data=["lo", "hi", "delta_pp"],
        labels={
            "expected": "Predicted (bucket mean)",
            "realized": "Realized hit rate",
        },
        range_x=[0.45, 1.0], range_y=[0.0, 1.0],
        color_continuous_scale="Viridis",
    )
    # y=x perfect-calibration diagonal.
    fig.add_shape(
        type="line", x0=0.5, y0=0.5, x1=1.0, y1=1.0,
        line=dict(color="gray", dash="dash"),
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Need more closed predictions to compute per-bucket calibration.")

# --- Breakdown table by regime x flag -------------------------------------
st.subheader("Breakdown by regime × flag")
if data["breakdown"]:
    bdf = pd.DataFrame(data["breakdown"])
    bdf["hit_rate"] = (bdf["hit_rate"] * 100).round(1).astype(str) + "%"
    st.dataframe(bdf, use_container_width=True, hide_index=True)
else:
    st.caption("No breakdown rows.")

# --- Ship criteria check button -------------------------------------------
st.divider()
st.subheader("v0.3 ship criteria check")
if st.button("▶ Run ship_criteria_check.py"):
    with st.spinner("Running..."):
        result = subprocess.run(
            ["python", "scripts/ship_criteria_check.py"],
            capture_output=True, text=True, timeout=60,
        )
    if result.returncode == 0:
        st.success("READY FOR PROMOTION")
    elif result.returncode == 2:
        st.error("NOT READY — see message below for next step")
    else:
        st.warning(f"Unexpected exit code {result.returncode}")
    st.code(result.stdout or "(no output)", language=None)
    if result.stderr:
        with st.expander("stderr"):
            st.code(result.stderr, language=None)
