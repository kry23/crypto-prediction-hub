"""Journal page — dated session journals + CHANGELOG as a newest-first feed.

Spec: docs/superpowers/specs/2026-06-07-journal-page-design.md
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.journal_loader import load_log_entries

require_auth()
st.title("📓 Journal")
st.caption("Session journals + changelog — newest first.")

# This file is at src/crypto_predictor/ui/pages/ -> parents[4] is the repo root.
_ROOT = Path(__file__).resolve().parents[4]


@st.cache_data(ttl=300)
def _load():
    return load_log_entries(_ROOT)


entries = _load()
if not entries:
    st.info("No journal entries found.")
else:
    for i, entry in enumerate(entries):
        with st.expander(entry.label, expanded=(i == 0)):
            st.markdown(entry.body)
