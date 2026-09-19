"""Step 1. Send any message to your bot, then run this."""
import _bootstrap  # noqa: F401
import httpx

import config

url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
data = httpx.get(url, timeout=15).json()

if not data.get("ok"):
    raise SystemExit(f"Telegram error: {data}")

results = data.get("result", [])
if not results:
    raise SystemExit(
        "No updates. Send your bot a message in Telegram first, then rerun.\n"
        "(If a webhook is already set, run scripts/set_webhook.py --delete first.)"
    )

seen = {}
for item in results:
    msg = item.get("message") or item.get("edited_message") or {}
    chat = msg.get("chat") or {}
    if chat.get("id"):
        seen[chat["id"]] = chat.get("username") or chat.get("first_name") or "?"

for chat_id, who in seen.items():
    print(f"chat_id={chat_id}   ({who})")
print("\nPut that number in ALLOWED_CHAT_IDS in your .env")
