"""Ask Claude page — TODO Task 7."""
import streamlit as st

from crypto_predictor.ui.auth import require_auth

email = require_auth()
st.title("Ask Claude")
st.info("This page is a placeholder. Implementation lands in UI Task 7.")
st.caption(f"Authenticated user: `{email}`")
