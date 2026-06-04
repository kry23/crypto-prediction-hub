"""Dashboard page — TODO Task 4."""
import streamlit as st

from crypto_predictor.ui.auth import require_auth

email = require_auth()
st.title("Dashboard")
st.info("This page is a placeholder. Implementation lands in UI Task 4.")
st.caption(f"Authenticated user: `{email}`")
