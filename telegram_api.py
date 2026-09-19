"""Thin Telegram Bot API wrapper. Sync on purpose - it is called from a
FastAPI background task, which runs sync functions in a threadpool."""
import logging

import httpx

import config

log = logging.getLogger(__name__)
BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def send_message(chat_id: int | str, text: str) -> None:
    try:
        response = httpx.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if response.status_code != 200:
            log.error("sendMessage failed: %s %s", response.status_code, response.text)
    except Exception:
        log.exception("sendMessage raised")
