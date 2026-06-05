"""Streamlit entry point. Run with:
    streamlit run src/crypto_predictor/ui/app.py
"""
from __future__ import annotations

import streamlit as st

from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.theme import inject_theme


def main() -> None:
    st.set_page_config(
        page_title="crypto-predictor",
        page_icon="🔮",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_theme()  # Midnight Desk — must follow set_page_config (first st call)

    email = require_auth()

    # Multi-page navigation (Streamlit 1.40+ pattern)
    pages = [
        st.Page(
            "pages/dashboard.py", title="Dashboard", icon="📊", default=True
        ),
        st.Page("pages/track_record.py", title="Track record", icon="📈"),
        st.Page("pages/operator.py", title="Operator", icon="🛠"),
        st.Page("pages/ask_claude.py", title="Ask Claude", icon="💬"),
    ]
    nav = st.navigation(pages, position="top")

    # Global header strip
    with st.container():
        cols = st.columns([3, 1, 1])
        cols[0].markdown("### 🔮 crypto-predictor")
        cols[1].caption(f"signed in: `{email}`")
        cols[2].caption("v1.0")

    st.divider()
    nav.run()


if __name__ == "__main__":
    main()
