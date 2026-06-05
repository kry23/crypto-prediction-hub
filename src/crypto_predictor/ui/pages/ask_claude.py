"""Ask Claude — server-side AI assistant with DB + file tool access.

Layout per spec §4.4:

* Conversation pane (full-width) via ``st.chat_message`` (history loaded
  from ``claude_chat_log`` keyed by the per-tab session UUID).
* Chat input row at the bottom; disabled when the daily $ cap is hit.
* Sidebar shows today's spend / cap and the current session id prefix.

Cost-cap gate runs *before* the chat input renders. When tripped the page
prints a banner and stops — no further Anthropic calls until 00:00 UTC.
"""
from __future__ import annotations

import os

import streamlit as st

from crypto_predictor.ui.auth import require_auth
from crypto_predictor.ui.claude_session import (
    call_claude,
    get_or_create_session_id,
    is_cost_capped,
    load_conversation,
    persist_turn,
)
from crypto_predictor.ui.claude_tools import TOOL_SCHEMAS
from crypto_predictor.ui.db import get_conn

SYSTEM_PROMPT = (
    "You are the crypto-predictor assistant. You can query the PostgreSQL "
    "database, read calibration JSONs, run analysis scripts, and read the "
    "session journal via tools. Be terse and data-driven. Surface "
    "uncertainty. Never make trading recommendations — describe what the "
    "model says, not what the user should do."
)


def render() -> None:
    email = require_auth()
    st.title("💬 Ask Claude")
    st.caption(f"Signed in: `{email}`")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.warning(
            "ANTHROPIC_API_KEY is not set. Add it to "
            "/etc/crypto-predictor/secrets.env and restart "
            "crypto-predictor-ui.service to enable Ask Claude."
        )
        st.stop()

    with get_conn() as conn:
        capped, today_usd, limit_usd = is_cost_capped(conn)

    st.sidebar.metric(
        "Today (Claude)",
        f"${today_usd:.2f}",
        delta=f"of ${limit_usd:.2f} cap",
        delta_color="off",
    )
    session_id = get_or_create_session_id()
    st.sidebar.caption(f"Session: `{session_id[:8]}`")

    if capped:
        st.error(
            f"Daily limit reached: ${today_usd:.2f} / ${limit_usd:.2f}. "
            "Resets at 00:00 UTC."
        )
        st.stop()

    with get_conn() as conn:
        history = load_conversation(conn, session_id)

    # Only user/assistant turns render as chat bubbles; tool plumbing stays
    # in tool_calls JSON and is not surfaced inline.
    for turn in history:
        if turn["role"] not in ("user", "assistant"):
            continue
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    prompt = st.chat_input(
        "Ask anything about predictions, calibration, or the model state..."
    )
    if not prompt:
        return

    with get_conn() as conn:
        persist_turn(
            conn, session_id=session_id, role="user", content=prompt,
        )
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            messages = [
                {"role": t["role"], "content": t["content"]}
                for t in history
                if t["role"] in ("user", "assistant") and t.get("content")
            ] + [{"role": "user", "content": prompt}]

            with get_conn() as conn:
                response = call_claude(
                    messages=messages,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    conn=conn,
                )

        st.markdown(response["content"] or "_(empty response)_")

    with get_conn() as conn:
        persist_turn(
            conn,
            session_id=session_id,
            role="assistant",
            content=response["content"],
            tool_calls=response.get("tool_uses"),
            tokens_in=response.get("tokens_in", 0),
            tokens_out=response.get("tokens_out", 0),
            cost_usd=response.get("cost_usd", 0.0),
        )
    st.rerun()


render()
