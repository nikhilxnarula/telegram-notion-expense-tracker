"""FastAPI webhook. Deliberately tiny - all logic lives in pipeline.py."""
import logging
from collections import deque

from fastapi import BackgroundTasks, FastAPI, Request

import config
from pipeline import handle_text
from telegram_api import send_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Telegram -> Notion expense bot")

# Telegram redelivers an update if we are slow or reply non-200. In-memory
# only, so a cold start forgets it - worst case is a rare duplicate row.
_seen_updates: deque[int] = deque(maxlen=500)


@app.get("/")
def health():
    return {"status": "ok"}


def _process(chat_id: int, text: str) -> None:
    send_message(chat_id, handle_text(text))


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    # Anyone can reach this URL, so the shared secret is the real gate.
    # Fail silently rather than 403 - do not confirm the endpoint exists.
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.TELEGRAM_WEBHOOK_SECRET:
        log.warning("rejected request with bad or missing secret token")
        return {"ok": True}

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    update_id = update.get("update_id")
    if update_id in _seen_updates:
        return {"ok": True}
    if update_id is not None:
        _seen_updates.append(update_id)

    message = update.get("message") or update.get("edited_message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text")

    if chat_id is None or not text:
        return {"ok": True}

    if config.ALLOWED_CHAT_IDS and str(chat_id) not in config.ALLOWED_CHAT_IDS:
        log.warning("ignored message from unlisted chat_id %s", chat_id)
        return {"ok": True}

    # Return 200 immediately; do the slow work after. Telegram gives us only
    # a few seconds before it assumes failure and retries.
    background.add_task(_process, chat_id, text)
    return {"ok": True}
