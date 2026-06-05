"""Claude conversation session: PG persistence + cost cap + tool loop.

This module deliberately wraps the bare Anthropic SDK (not the higher-level
Claude Agent SDK) for v1.0:

* Streamlit is not asyncio-friendly; the agent SDK's event-loop expectations
  bite back in a synchronous page run.
* We only need one short tool-use loop per turn — easy to do by hand.
* Smaller dependency surface; only ``anthropic>=0.40`` is required.

Public surface:

    get_or_create_session_id()          — per-tab UUID
    todays_claude_cost(conn) -> float   — sum cost_usd over today (UTC)
    is_cost_capped(conn) -> (bool, today, limit)
    load_conversation(conn, sid) -> [{role, content, ...}]
    persist_turn(conn, *, ...)          — INSERT one chat turn
    call_claude(messages, system, tools, conn) -> {content, tool_uses,
                                                    tokens_in, tokens_out,
                                                    cost_usd}
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only without the SDK
    anthropic = None  # type: ignore[assignment]

try:
    import streamlit as st
except ImportError:  # pragma: no cover - tests stub streamlit
    st = None  # type: ignore[assignment]

from crypto_predictor.ui.claude_tools import (
    TOOL_DISPATCH,
    TOOL_SCHEMAS,
    TOOLS_NEEDING_CONN,
)

# --- pricing (claude-opus-4-7 approx, USD per token; cap-guardrail use only)
_PRICE_IN_PER_TOKEN = 15e-6   # $15 / Mtok
_PRICE_OUT_PER_TOKEN = 75e-6  # $75 / Mtok

_DEFAULT_MODEL = "claude-opus-4-7"
_DEFAULT_LIMIT_USD = 5.0
_DEFAULT_MAX_TURNS = 8  # safeguard against runaway tool loops


# ---------------------------------------------------------------------------
# session id
# ---------------------------------------------------------------------------

def get_or_create_session_id() -> str:
    """Return a stable UUID for the current Streamlit tab.

    Stored under ``st.session_state['claude_session_id']`` so a tab refresh
    (which keeps session_state) keeps the same conversation. A new tab
    gets a new id and therefore a clean slate.
    """
    if st is None:  # pragma: no cover - tests stub streamlit
        return str(uuid.uuid4())
    state = st.session_state
    sid = state.get("claude_session_id") if hasattr(state, "get") else None
    if sid:
        return sid
    sid = str(uuid.uuid4())
    state["claude_session_id"] = sid
    return sid


# ---------------------------------------------------------------------------
# cost accounting
# ---------------------------------------------------------------------------

def todays_claude_cost(conn) -> float:
    """Sum ``cost_usd`` over today (UTC) from ``claude_chat_log``."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM claude_chat_log
            WHERE created_at >= date_trunc('day',
                                            (now() AT TIME ZONE 'UTC'))
            """
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return 0.0
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return 0.0


def _read_limit_env() -> float:
    raw = os.environ.get("CLAUDE_DAILY_USD_LIMIT")
    if raw is None or raw == "":
        return _DEFAULT_LIMIT_USD
    try:
        return float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT_USD


def is_cost_capped(conn) -> tuple[bool, float, float]:
    """Return ``(capped, today_usd, limit_usd)``.

    ``capped`` is True when ``today_usd >= limit_usd``.
    """
    limit = _read_limit_env()
    today = todays_claude_cost(conn)
    return today >= limit, today, limit


def _compute_cost(tokens_in: int, tokens_out: int) -> float:
    return float(tokens_in) * _PRICE_IN_PER_TOKEN + \
        float(tokens_out) * _PRICE_OUT_PER_TOKEN


# ---------------------------------------------------------------------------
# conversation persistence
# ---------------------------------------------------------------------------

def load_conversation(conn, session_id: str) -> list[dict]:
    """Return all turns for ``session_id`` ordered oldest -> newest."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, content, tool_calls, tokens_in, tokens_out,
                   cost_usd, created_at
            FROM claude_chat_log
            WHERE session_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    out: list[dict] = []
    for row in rows:
        role, content, tool_calls, t_in, t_out, cost, created_at = row
        tool_calls_obj: Any = tool_calls
        if isinstance(tool_calls, str):
            try:
                tool_calls_obj = json.loads(tool_calls)
            except (TypeError, ValueError):
                tool_calls_obj = None
        out.append({
            "role": role,
            "content": content,
            "tool_calls": tool_calls_obj,
            "tokens_in": int(t_in) if t_in is not None else 0,
            "tokens_out": int(t_out) if t_out is not None else 0,
            "cost_usd": float(cost) if cost is not None else 0.0,
            "created_at": (
                created_at.isoformat()
                if isinstance(created_at, datetime) else created_at
            ),
        })
    return out


def persist_turn(
    conn,
    *,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """INSERT a single conversation turn into ``claude_chat_log``."""
    tool_calls_payload = (
        json.dumps(tool_calls) if tool_calls is not None else None
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claude_chat_log
                (session_id, role, content, tool_calls,
                 tokens_in, tokens_out, cost_usd, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id, role, content, tool_calls_payload,
                int(tokens_in), int(tokens_out), float(cost_usd),
                datetime.now(timezone.utc),
            ),
        )
    # psycopg autocommit may be off; let caller / context manager commit.
    try:
        conn.commit()
    except Exception:  # pragma: no cover - already-committed pools, etc.
        pass


# ---------------------------------------------------------------------------
# Anthropic client + tool loop
# ---------------------------------------------------------------------------

def _build_client():
    if anthropic is None:
        raise RuntimeError(
            "anthropic SDK is not installed; "
            "run `pip install anthropic>=0.40` in the venv."
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=api_key)


def dispatch_tool(name: str, tool_input: dict, conn=None) -> Any:
    """Execute one tool by name. Injects ``conn`` for DB-backed tools."""
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    kwargs: dict[str, Any] = dict(tool_input or {})
    if name in TOOLS_NEEDING_CONN:
        if conn is None:
            return {"error": f"tool '{name}' needs a DB connection"}
        kwargs["conn"] = conn
    try:
        result = fn(**kwargs)
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # pragma: no cover - defensive surface
        return {"error": f"{name} raised {type(exc).__name__}: {exc}"}
    return result


def _tool_result_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def call_claude(
    *,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
    conn=None,
    model: str | None = None,
    max_turns: int = _DEFAULT_MAX_TURNS,
) -> dict:
    """Send ``messages`` to Anthropic and resolve any ``tool_use`` blocks.

    Returns a dict ``{content, tool_uses, tokens_in, tokens_out, cost_usd}``
    where ``content`` is the final assistant text, ``tool_uses`` is a list
    of ``{name, input, result}`` records (one per executed tool), and the
    cost is a coarse upper bound (no cache discount applied).
    """
    client = _build_client()
    model = model or os.environ.get("ANTHROPIC_MODEL") or _DEFAULT_MODEL
    tools = tools if tools is not None else TOOL_SCHEMAS

    # Prompt caching: cache the system prompt + tool schemas as the prefix
    # so repeated turns in the same session don't re-pay for them.
    system_blocks = [{
        "type": "text",
        "text": system,
        "cache_control": {"type": "ephemeral"},
    }]

    convo: list[dict] = list(messages)
    tool_uses_log: list[dict] = []
    total_in = 0
    total_out = 0

    for _ in range(max(1, int(max_turns))):
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_blocks,
            tools=tools,
            messages=convo,
        )

        usage = getattr(resp, "usage", None)
        if usage is not None:
            total_in += int(getattr(usage, "input_tokens", 0) or 0)
            total_in += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            total_in += int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            total_out += int(getattr(usage, "output_tokens", 0) or 0)

        content_blocks = list(getattr(resp, "content", []) or [])
        stop_reason = getattr(resp, "stop_reason", None)

        if stop_reason != "tool_use":
            text_parts = []
            for block in content_blocks:
                if getattr(block, "type", None) == "text":
                    text_parts.append(getattr(block, "text", ""))
            final_text = "\n".join(p for p in text_parts if p).strip()
            return {
                "content": final_text,
                "tool_uses": tool_uses_log,
                "tokens_in": total_in,
                "tokens_out": total_out,
                "cost_usd": _compute_cost(total_in, total_out),
            }

        # Echo the assistant turn back into the convo, then resolve tools.
        assistant_blocks = []
        tool_result_blocks: list[dict] = []
        for block in content_blocks:
            btype = getattr(block, "type", None)
            if btype == "text":
                assistant_blocks.append({
                    "type": "text",
                    "text": getattr(block, "text", ""),
                })
            elif btype == "tool_use":
                name = getattr(block, "name", "")
                tool_input = getattr(block, "input", {}) or {}
                tool_id = getattr(block, "id", "")
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": tool_input,
                })
                result = dispatch_tool(name, tool_input, conn=conn)
                tool_uses_log.append({
                    "name": name,
                    "input": tool_input,
                    "result": result,
                })
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": _tool_result_content(result),
                })
        convo.append({"role": "assistant", "content": assistant_blocks})
        if tool_result_blocks:
            convo.append({"role": "user", "content": tool_result_blocks})

    # Tool loop budget exhausted.
    return {
        "content": (
            "[tool loop reached max turns; stopping. "
            "Inspect tool_uses for partial results.]"
        ),
        "tool_uses": tool_uses_log,
        "tokens_in": total_in,
        "tokens_out": total_out,
        "cost_usd": _compute_cost(total_in, total_out),
    }
