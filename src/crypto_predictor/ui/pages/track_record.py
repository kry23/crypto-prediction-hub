"""Track Record page — TODO Task 5."""
import streamlit as st

from crypto_predictor.ui.auth import require_auth

email = require_auth()
st.title("Track record")
st.info("This page is a placeholder. Implementation lands in UI Task 5.")
st.caption(f"Authenticated user: `{email}`")
