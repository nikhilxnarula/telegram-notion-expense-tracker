"""Central env loading. Import this everywhere instead of reading os.environ."""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Explicit path so the scripts/ helpers find .env too, whatever the cwd.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


TELEGRAM_BOT_TOKEN = _required("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET = _required("TELEGRAM_WEBHOOK_SECRET")
ALLOWED_CHAT_IDS = {
    part.strip()
    for part in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if part.strip()
}

def _normalize_notion_id(raw: str) -> str:
    """Accept a bare id, a dashed UUID, or a full Notion URL.

    A database URL looks like:
        https://notion.so/<workspace>/<Page-Title>-<32 hex>?v=<32 hex view id>
    The id is the LAST 32 hex characters of the path - the title slug comes
    before it, and the v= value is the view id, not the database.
    """
    value = raw.strip().strip('"').strip("'")
    path = value.split("?", 1)[0]           # drop the ?v=<view id>
    candidates = re.findall(r"[0-9a-fA-F]{32}", path.replace("-", ""))
    if not candidates:
        raise RuntimeError(
            f"Could not find a 32-character database id in NOTION_DATABASE_ID={raw!r}. "
            "Open the database as a full page, use ... -> Copy link, and paste that."
        )
    return candidates[-1].lower()


NOTION_API_KEY = _required("NOTION_API_KEY")
NOTION_DATABASE_ID = _normalize_notion_id(_required("NOTION_DATABASE_ID"))

GEMINI_API_KEY = _required("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "Rs")
