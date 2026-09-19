"""Free-text message -> structured Expense, via Gemini."""
from datetime import datetime
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import config
from notion_writer import get_category_options

client = genai.Client(api_key=config.GEMINI_API_KEY)


class Expense(BaseModel):
    """Deliberately has no Optional/union fields - some model versions
    handle those badly in a response schema. Sentinels are used instead:
    amount == 0 means 'not found', is_expense == False means 'not an expense'."""

    is_expense: bool = Field(description="False if the message is not about spending money")
    name: str = Field(description="Short description: merchant, item, or purpose")
    amount: float = Field(description="Numeric amount only, no currency symbol. 0 if absent")
    category: str = Field(description="Must be copied exactly from the allowed list")
    date: str = Field(description="ISO date YYYY-MM-DD")
    confidence: float = Field(description="0.0 to 1.0")


PROMPT = """You extract a single expense record from a short personal message.

Today's date is {today} (timezone {tz}). Resolve relative dates like
"yesterday", "last Friday", "2 days ago" against that date. If no date is
mentioned at all, use today.

The Category MUST be copied character-for-character from this list:
{categories}
Pick the closest fit. If nothing fits well, choose the most general option
available in the list.

Amount conventions in this user's messages:
- "Rs", "rs.", the rupee sign, or no symbol at all all mean rupees
- "1.2k" means 1200; "2 lakh" means 200000
- If the user says their share of a split, extract only their share
- If no amount appears anywhere, set amount to 0

Set is_expense to false for greetings, questions, or anything that is not a
record of money spent.

Examples:
"chai 40" -> name "Chai", amount 40
"uber to airport rs 680 yesterday" -> name "Uber to airport", amount 680, date = yesterday
"1.2k groceries at dmart" -> name "Groceries at DMart", amount 1200
"split dinner, my share 450" -> name "Dinner (split)", amount 450
"how much did I spend?" -> is_expense false

Message:
{message}
"""


def _snap_to_allowed(value: str, allowed: tuple[str, ...]) -> str:
    """Force the model's category onto a real Notion option."""
    for option in allowed:
        if option.lower() == value.lower().strip():
            return option
    for option in allowed:
        if option.lower() in value.lower() or value.lower() in option.lower():
            return option
    for fallback in ("Other", "Misc", "Miscellaneous", "Uncategorized"):
        if fallback in allowed:
            return fallback
    return allowed[-1]


def _strip_fences(text: str) -> str:
    """Some model versions wrap JSON in ```json fences despite the mime type."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


_JSON_HINT = (
    "\n\nReturn ONLY a JSON object with these keys: is_expense (boolean), "
    "name (string), amount (number), category (string), "
    "date (string, YYYY-MM-DD), confidence (number 0-1)."
)


def _generate(prompt: str) -> str:
    """Ask for schema-constrained JSON; fall back to plain JSON mode if this
    SDK version rejects the schema argument."""
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Expense,
                temperature=0,
            ),
        )
    except TypeError:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt + _JSON_HINT,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            raise RuntimeError(
                f"Model '{config.GEMINI_MODEL}' is not available to your API key. "
                "Run: python scripts/list_models.py, then set GEMINI_MODEL in .env"
            ) from exc
        raise

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, Expense):
        return parsed.model_dump_json()
    return _strip_fences(response.text)


def extract(message: str) -> Expense:
    categories = get_category_options()
    today = datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()

    prompt = PROMPT.format(
        today=today,
        tz=config.TIMEZONE,
        categories="\n".join(f"- {c}" for c in categories),
        message=message,
    )

    expense = Expense.model_validate_json(_generate(prompt))
    expense.category = _snap_to_allowed(expense.category, categories)
    return expense
