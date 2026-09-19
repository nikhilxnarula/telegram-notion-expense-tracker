"""Step 2. Print model IDs your key can actually use, so GEMINI_MODEL is valid."""
import _bootstrap  # noqa: F401
from google import genai

import config

client = genai.Client(api_key=config.GEMINI_API_KEY)

print("Models supporting generateContent:\n")
for model in client.models.list():
    actions = getattr(model, "supported_actions", None) or []
    if not actions or "generateContent" in actions:
        print(" ", model.name.replace("models/", ""))

print(f"\nCurrently configured: GEMINI_MODEL={config.GEMINI_MODEL}")
print("If it is not in the list above, change it in .env")
