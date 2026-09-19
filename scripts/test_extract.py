"""Step 4. Exercise the LLM only - writes nothing to Notion."""
import _bootstrap  # noqa: F401
from extractor import extract

SAMPLES = [
    "chai 40",
    "uber to airport rs 680 yesterday",
    "1.2k groceries at dmart",
    "split dinner, my share 450",
    "recharge 299",
    "how much did I spend this month?",
    "lunch",
]

for sample in SAMPLES:
    try:
        result = extract(sample)
    except Exception as exc:
        print(f"{sample!r}\n   ERROR: {exc}\n")
        continue
    if not result.is_expense:
        print(f"{sample!r}\n   -> not an expense (correct for the last two)\n")
        continue
    print(
        f"{sample!r}\n"
        f"   -> {result.name} | {result.amount} | {result.category} | "
        f"{result.date} | conf {result.confidence}\n"
    )
