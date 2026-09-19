"""Free-text message -> structured Expense, via Amazon Bedrock.

Structured output is done with a forced tool call rather than "reply in JSON":
the model must emit arguments matching the tool's inputSchema, which is
generated from the Expense pydantic model.
"""
import difflib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

import config
from notion_writer import get_category_options

log = logging.getLogger(__name__)

# Adaptive retries because Bedrock throttles on-demand capacity; a single
# expense message is cheap to retry and a failure here means a lost entry.
_boto_config = Config(
    region_name=config.AWS_REGION,
    retries={"max_attempts": 4, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=30,
)
client = boto3.client("bedrock-runtime", config=_boto_config)

TOOL_NAME = "record_expense"


class Expense(BaseModel):
    """Deliberately has no Optional/union fields - they translate badly into
    tool input schemas across model families. Sentinels instead:
    amount == 0 means 'not found', is_expense == False means 'not an expense'."""

    is_expense: bool = Field(description="False if the message is not about spending money")
    name: str = Field(description="Short description: merchant, item, or purpose")
    amount: float = Field(description="Numeric amount only, no currency symbol. 0 if absent")
    category: str = Field(description="Must be copied exactly from the allowed list")
    date: str = Field(description="ISO date YYYY-MM-DD")
    confidence: float = Field(description="0.0 to 1.0")


SYSTEM_PROMPT = """You extract a single expense record from a short personal message.

Today's date is {today} (timezone {tz}). Resolve relative dates like
"yesterday", "last Friday", "2 days ago" against that date. If no date is
mentioned at all, use today.

The category MUST be copied character-for-character from this list:
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

Always call the {tool} tool with your answer."""

_JSON_HINT = (
    "\n\nReturn ONLY a JSON object with these keys: is_expense (boolean), "
    "name (string), amount (number), category (string), "
    "date (string, YYYY-MM-DD), confidence (number 0-1)."
)


def _snap_to_allowed(value: str, allowed: tuple[str, ...]) -> str:
    """Force the model's category onto a real Notion option.

    Four tiers: exact, substring, fuzzy, then a generic bucket. The fuzzy tier
    matters more than it looks - 'grocery' and 'Groceries' share no substring
    relationship, so without it a near-miss lands in 'Other'.
    """
    needle = value.lower().strip()
    by_lower = {option.lower(): option for option in allowed}

    if needle in by_lower:
        return by_lower[needle]

    for lowered, option in by_lower.items():
        if lowered in needle or needle in lowered:
            return option

    close = difflib.get_close_matches(needle, list(by_lower), n=1, cutoff=0.6)
    if close:
        return by_lower[close[0]]

    for fallback in ("Other", "Misc", "Miscellaneous", "Uncategorized"):
        if fallback in allowed:
            return fallback
    return allowed[-1]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _tool_config(forced: bool) -> dict:
    schema = Expense.model_json_schema()
    schema.pop("title", None)
    # Replace the class docstring, which is a note to maintainers, not the model.
    schema["description"] = "One expense parsed from the user's message."
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": TOOL_NAME,
                    "description": "Record one expense parsed from the user's message.",
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": TOOL_NAME}} if forced else {"any": {}},
    }


def _converse(system_prompt: str, message: str, tool_config: dict | None) -> dict:
    kwargs = {
        "modelId": config.BEDROCK_MODEL_ID,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": message}]}],
        "inferenceConfig": {"temperature": 0, "maxTokens": 512},
    }
    if tool_config is not None:
        kwargs["toolConfig"] = tool_config
    return client.converse(**kwargs)


def _friendly_client_error(exc: ClientError) -> Exception:
    """Turn the three Bedrock errors you will actually hit into instructions."""
    error = exc.response.get("Error", {})
    code = error.get("Code", "")
    message = error.get("Message", "")
    lowered = message.lower()

    if code == "AccessDeniedException":
        return RuntimeError(
            f"Bedrock denied access to '{config.BEDROCK_MODEL_ID}' in "
            f"{config.AWS_REGION}. Either your IAM principal lacks "
            "bedrock:InvokeModel, or model access is not enabled for this model "
            "in the Bedrock console (Model access page). Both are required."
        )
    if "inference profile" in lowered or "on-demand throughput isn" in lowered:
        return RuntimeError(
            f"'{config.BEDROCK_MODEL_ID}' cannot be called directly - it needs a "
            "cross-region inference profile ID (usually the same id with a 'us.' "
            "or 'eu.' prefix). Run: python scripts/list_models.py"
        )
    if code == "ValidationException" and "model identifier" in lowered:
        return RuntimeError(
            f"'{config.BEDROCK_MODEL_ID}' is not a valid model id in "
            f"{config.AWS_REGION}. Run: python scripts/list_models.py"
        )
    return exc


def _tool_input(response: dict) -> dict | None:
    for block in response["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"]
    return None


def _text(response: dict) -> str:
    return "".join(
        block["text"]
        for block in response["output"]["message"]["content"]
        if "text" in block
    )


def _generate(system_prompt: str, message: str) -> Expense:
    """Forced tool call, then any-tool, then plain JSON text. Each tier covers
    a model family that does not support the tier above it."""
    try:
        response = _converse(system_prompt, message, _tool_config(forced=True))
    except ClientError as exc:
        lowered = str(exc).lower()
        if "toolchoice" in lowered or "tool choice" in lowered:
            log.warning("model rejected forced toolChoice, falling back to 'any'")
            try:
                response = _converse(system_prompt, message, _tool_config(forced=False))
            except ClientError as inner:
                raise _friendly_client_error(inner) from inner
        elif "tool" in lowered and "not support" in lowered:
            log.warning("model does not support tools, falling back to JSON text")
            response = _converse(system_prompt + _JSON_HINT, message, None)
        else:
            raise _friendly_client_error(exc) from exc

    payload = _tool_input(response)
    if payload is not None:
        return Expense.model_validate(payload)

    raw = _strip_fences(_text(response))
    if not raw:
        raise RuntimeError(
            "Bedrock returned neither a tool call nor text. "
            f"stopReason={response.get('stopReason')}"
        )
    return Expense.model_validate(json.loads(raw))


def extract(message: str) -> Expense:
    categories = get_category_options()
    today = datetime.now(ZoneInfo(config.TIMEZONE)).date().isoformat()

    system_prompt = SYSTEM_PROMPT.format(
        today=today,
        tz=config.TIMEZONE,
        categories="\n".join(f"- {c}" for c in categories),
        tool=TOOL_NAME,
    )

    expense = _generate(system_prompt, message)
    expense.category = _snap_to_allowed(expense.category, categories)
    return expense
