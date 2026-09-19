"""Step 6. Fire a fake Telegram update at a locally running server.

    uvicorn main:app --reload          # in one terminal
    python scripts/fake_update.py "chai 40"    # in another
"""
import sys

import _bootstrap  # noqa: F401
import httpx

import config

text = " ".join(sys.argv[1:]) or "chai 40"
chat_id = next(iter(config.ALLOWED_CHAT_IDS), "1")

response = httpx.post(
    "http://127.0.0.1:8000/webhook",
    headers={"X-Telegram-Bot-Api-Secret-Token": config.TELEGRAM_WEBHOOK_SECRET},
    json={
        "update_id": __import__("random").randint(1, 10**9),
        "message": {
            "message_id": 1,
            "chat": {"id": int(chat_id), "type": "private"},
            "text": text,
        },
    },
    timeout=60,
)
print(response.status_code, response.json())
print("Now check the uvicorn logs, your Telegram chat, and Notion.")
