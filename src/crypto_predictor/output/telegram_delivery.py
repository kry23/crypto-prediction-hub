"""Telegram delivery via Bot API (httpx)."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(*, bot_token: str, chat_id: str, text: str,
                 disable_preview: bool = True) -> bool:
    """Send a Telegram message via the Bot API. Returns True on success."""
    if not bot_token or not chat_id:
        log.warning("telegram_skipped_no_token")
        return False
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_preview,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=20.0)
        if resp.status_code == 200:
            return True
        log.warning("telegram_send_failed",
                    status=resp.status_code, body=resp.text[:200])
        return False
    except Exception as exc:
        log.warning("telegram_send_exception", error=str(exc))
        return False
