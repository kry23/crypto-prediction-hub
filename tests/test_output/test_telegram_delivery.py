from unittest.mock import MagicMock, patch

from crypto_predictor.output.telegram_delivery import send_message


def test_send_message_calls_telegram_api(monkeypatch):
    fake_resp = MagicMock(status_code=200, text="ok")
    fake_post = MagicMock(return_value=fake_resp)
    monkeypatch.setattr("httpx.post", fake_post)
    ok = send_message(bot_token="FAKE", chat_id="123",
                      text="hello", disable_preview=True)
    assert ok is True
    args, kwargs = fake_post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "123"
    assert kwargs["json"]["text"] == "hello"


def test_send_message_returns_false_on_error(monkeypatch):
    fake_resp = MagicMock(status_code=500, text="server error")
    fake_post = MagicMock(return_value=fake_resp)
    monkeypatch.setattr("httpx.post", fake_post)
    ok = send_message(bot_token="FAKE", chat_id="123", text="x")
    assert ok is False


def test_send_message_skips_when_no_token():
    ok = send_message(bot_token="", chat_id="123", text="x")
    assert ok is False
