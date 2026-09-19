"""The actual application logic, independent of Telegram and of FastAPI.
Runnable on its own:  python pipeline.py "chai 40"
"""
import logging

import config
from extractor import extract
from notion_writer import create_expense

log = logging.getLogger(__name__)


def handle_text(message: str) -> str:
    """Take a raw message, return the reply text to send back."""
    text = (message or "").strip()
    if not text:
        return "Send me something like: <code>chai 40</code>"

    try:
        expense = extract(text)
    except Exception:
        log.exception("extraction failed")
        return "Could not read that. Try: <code>chai 40</code>"

    if not expense.is_expense:
        return "That does not look like an expense. Try: <code>chai 40</code>"

    if expense.amount <= 0:
        return f"Got \"{expense.name}\" but no amount. How much was it?"

    try:
        url = create_expense(
            name=expense.name,
            amount=expense.amount,
            category=expense.category,
            on_date=expense.date,
        )
    except Exception:
        log.exception("notion write failed")
        return "Parsed it, but saving to Notion failed. Check the server logs."

    flag = "" if expense.confidence >= 0.6 else "  (low confidence, check it)"
    return (
        f"Saved  {config.CURRENCY_SYMBOL}{expense.amount:,.0f}  |  "
        f"{expense.category}  |  {expense.date}\n"
        f"<a href=\"{url}\">{expense.name}</a>{flag}"
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print('Usage: python pipeline.py "chai 40"')
        raise SystemExit(1)
    print(handle_text(" ".join(sys.argv[1:])))
