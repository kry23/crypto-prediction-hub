"""Cloudflare Access identity extraction.

In production the UI sits behind Cloudflare Tunnel + Access; the access
proxy injects the verified email as a request header. The Streamlit
process trusts that header because the only way to reach :8501 is
through the tunnel.

Locally (dev mode) the header is absent; we fall back to a placeholder
identity when the ENV env var is set to 'dev'.

Note: `st.context.headers` requires Streamlit 1.40+.
"""
from __future__ import annotations

import os

import streamlit as st

_HEADER = "Cf-Access-Authenticated-User-Email"


def current_user_email() -> str | None:
    """Read the Cloudflare-Access-injected email header. None when running
    locally without the header set."""
    try:
        return st.context.headers.get(_HEADER)
    except (AttributeError, KeyError, Exception):
        return None


def require_auth() -> str:
    """Block page rendering if no email; return email when present.
    Falls back to a placeholder identity in dev mode (ENV=dev)."""
    email = current_user_email()
    if email:
        return email
    if os.environ.get("ENV", "prod") == "dev":
        return "dev@local"
    st.error("Authentication required. This UI is gated by Cloudflare Access.")
    st.stop()
    return ""  # unreachable, satisfies type checker
