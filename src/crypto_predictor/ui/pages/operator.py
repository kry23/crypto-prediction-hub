"""Operator page — TODO Task 6."""
import streamlit as st

from crypto_predictor.ui.auth import require_auth

email = require_auth()
st.title("Operator")
st.info("This page is a placeholder. Implementation lands in UI Task 6.")
st.caption(f"Authenticated user: `{email}`")
