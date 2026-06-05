"""Unit tests for ``crypto_predictor.ui.claude_session``.

The Anthropic client is replaced with a small fake that scripts the
``messages.create(...)`` return values, so we exercise the tool-use loop
without touching the real API.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from crypto_predictor.ui import claude_session


# ---------------------------------------------------------------------------
# is_cost_capped
# ---------------------------------------------------------------------------

def test_is_cost_capped_under_limit_returns_false():
    with patch.dict("os.environ", {"CLAUDE_DAILY_USD_LIMIT": "5.0"}):
        with patch(
            "crypto_predictor.ui.claude_session.todays_claude_cost",
            return_value=2.0,
        ):
            capped, today, limit = claude_session.is_cost_capped(MagicMock())
    assert capped is False
    assert today == 2.0
    assert limit == 5.0


def test_is_cost_capped_over_limit_returns_true():
    with patch.dict("os.environ", {"CLAUDE_DAILY_USD_LIMIT": "5.0"}):
        with patch(
            "crypto_predictor.ui.claude_session.todays_claude_cost",
            return_value=6.0,
        ):
            capped, today, limit = claude_session.is_cost_capped(MagicMock())
    assert capped is True
    assert today == 6.0


def test_is_cost_capped_default_limit_is_five():
    with patch.dict("os.environ", {}, clear=True):
        with patch(
            "crypto_predictor.ui.claude_session.todays_claude_cost",
            return_value=0.0,
        ):
            _, _, limit = claude_session.is_cost_capped(MagicMock())
    assert limit == 5.0


def test_is_cost_capped_invalid_env_falls_back_to_default():
    with patch.dict("os.environ", {"CLAUDE_DAILY_USD_LIMIT": "nan?"}):
        with patch(
            "crypto_predictor.ui.claude_session.todays_claude_cost",
            return_value=0.0,
        ):
            _, _, limit = claude_session.is_cost_capped(MagicMock())
    assert limit == 5.0


# ---------------------------------------------------------------------------
# todays_claude_cost
# ---------------------------------------------------------------------------

def test_todays_claude_cost_zero_when_no_rows():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (0,)
    assert claude_session.todays_claude_cost(conn) == 0.0


def test_todays_claude_cost_sums_decimal_values():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (3.42,)
    assert claude_session.todays_claude_cost(conn) == 3.42


# ---------------------------------------------------------------------------
# persist_turn
# ---------------------------------------------------------------------------

def test_persist_turn_encodes_tool_calls_as_json():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    tool_calls = [{"name": "query_predictions", "input": {"limit": 3}}]
    claude_session.persist_turn(
        conn, session_id="sid-1", role="assistant",
        content="hi", tool_calls=tool_calls,
        tokens_in=10, tokens_out=20, cost_usd=0.001,
    )
    args = cur.execute.call_args[0][1]
    # 4th column (index 3) is tool_calls.
    assert json.loads(args[3]) == tool_calls
    assert args[1] == "assistant"
    assert args[2] == "hi"
    assert args[4] == 10
    assert args[5] == 20
    assert args[6] == 0.001


def test_persist_turn_null_tool_calls_when_absent():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    claude_session.persist_turn(
        conn, session_id="sid-2", role="user", content="hi",
    )
    assert cur.execute.call_args[0][1][3] is None


# ---------------------------------------------------------------------------
# load_conversation
# ---------------------------------------------------------------------------

def test_load_conversation_returns_ordered_dicts():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [
        ("user", "q1", None, 0, 0, 0.0, None),
        ("assistant", "a1", json.dumps([{"name": "x"}]),
         5, 7, 0.0002, None),
    ]
    rows = claude_session.load_conversation(conn, "sid")
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[1]["tool_calls"] == [{"name": "x"}]


# ---------------------------------------------------------------------------
# call_claude (full tool-use loop, mocked SDK)
# ---------------------------------------------------------------------------

class _Block:
    """Stand-in for an Anthropic content block (text or tool_use)."""

    def __init__(self, *, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class _Usage:
    def __init__(self, input_tokens=0, output_tokens=0,
                 cache_read_input_tokens=0,
                 cache_creation_input_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens


class _Response:
    def __init__(self, *, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


def _fake_client(responses):
    """Build a fake Anthropic client whose ``messages.create`` yields the
    given responses in order."""
    client = MagicMock()
    client.messages.create.side_effect = responses
    return client


def test_call_claude_no_tool_use_returns_final_text(monkeypatch):
    fake_client = _fake_client([
        _Response(
            content=[_Block(type="text", text="hello world")],
            stop_reason="end_turn",
            usage=_Usage(input_tokens=100, output_tokens=10),
        ),
    ])
    monkeypatch.setattr(
        claude_session, "_build_client", lambda: fake_client,
    )
    out = claude_session.call_claude(
        messages=[{"role": "user", "content": "hi"}],
        system="sys",
        tools=[],
    )
    assert out["content"] == "hello world"
    assert out["tokens_in"] == 100
    assert out["tokens_out"] == 10
    # Cost = 100*15e-6 + 10*75e-6 = 0.0015 + 0.00075 = 0.00225
    assert abs(out["cost_usd"] - 0.00225) < 1e-9
    assert out["tool_uses"] == []


def test_call_claude_executes_tool_use_loop(monkeypatch):
    """First turn: tool_use; second turn: end_turn with final text."""
    # Spy on dispatch_tool to confirm the loop hands input through.
    captured: list = []

    def fake_dispatch(name, tool_input, conn=None):
        captured.append((name, tool_input))
        return {"ok": True, "n": 7}

    monkeypatch.setattr(claude_session, "dispatch_tool", fake_dispatch)

    fake_client = _fake_client([
        _Response(
            content=[_Block(
                type="tool_use",
                id="tu_1",
                name="query_predictions",
                input={"limit": 5},
            )],
            stop_reason="tool_use",
            usage=_Usage(input_tokens=50, output_tokens=5),
        ),
        _Response(
            content=[_Block(type="text", text="done")],
            stop_reason="end_turn",
            usage=_Usage(input_tokens=70, output_tokens=15),
        ),
    ])
    monkeypatch.setattr(
        claude_session, "_build_client", lambda: fake_client,
    )

    out = claude_session.call_claude(
        messages=[{"role": "user", "content": "ask"}],
        system="sys",
        tools=[],
        conn=MagicMock(),
    )
    assert out["content"] == "done"
    assert len(out["tool_uses"]) == 1
    assert out["tool_uses"][0]["name"] == "query_predictions"
    assert out["tool_uses"][0]["input"] == {"limit": 5}
    assert out["tool_uses"][0]["result"] == {"ok": True, "n": 7}
    # Tokens summed across both turns.
    assert out["tokens_in"] == 120
    assert out["tokens_out"] == 20
    assert captured == [("query_predictions", {"limit": 5})]


def test_call_claude_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        claude_session.call_claude(
            messages=[{"role": "user", "content": "x"}],
            system="sys",
            tools=[],
        )
    except RuntimeError as exc:
        assert "ANTHROPIC_API_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


# ---------------------------------------------------------------------------
# dispatch_tool
# ---------------------------------------------------------------------------

def test_dispatch_tool_unknown_tool_returns_error():
    out = claude_session.dispatch_tool("nope", {})
    assert "error" in out


def test_dispatch_tool_db_tool_without_conn_returns_error():
    out = claude_session.dispatch_tool("query_predictions", {"limit": 1})
    assert "error" in out
    assert "DB connection" in out["error"]
