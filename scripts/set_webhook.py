"""Step 7. Point Telegram at your deployed URL.

    python scripts/set_webhook.py https://xxx.run.app
    python scripts/set_webhook.py --info
    python scripts/set_webhook.py --delete
"""
import sys

import _bootstrap  # noqa: F401
import httpx

import config

BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def show_info():
    print(httpx.get(f"{BASE}/getWebhookInfo", timeout=15).json())


if len(sys.argv) < 2:
    raise SystemExit(__doc__)

arg = sys.argv[1]

if arg == "--info":
    show_info()
elif arg == "--delete":
    print(httpx.post(f"{BASE}/deleteWebhook", timeout=15).json())
else:
    url = arg.rstrip("/") + "/webhook"
    response = httpx.post(
        f"{BASE}/setWebhook",
        json={
            "url": url,
            "secret_token": config.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        },
        timeout=15,
    ).json()
    print(response)
    print("\nWebhook info:")
    show_info()
