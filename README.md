# Telegram -> Notion expense tracker

Send `chai 40` to a Telegram bot; an LLM parses it; a row appears in Notion.

## Notion schema this expects

| Property | Type   |
|----------|--------|
| Name     | Title  |
| Amount   | Number |
| Date     | Date   |
| Category | Select |

Category options are read from Notion at runtime, so adding one there needs
no code change.

## Files

| File | Purpose |
|------|---------|
| `config.py` | env loading, fails fast on anything missing |
| `notion_writer.py` | reads Category options, creates rows |
| `extractor.py` | message -> `Expense` via Gemini structured output |
| `pipeline.py` | glue; runnable standalone for testing |
| `telegram_api.py` | sendMessage |
| `main.py` | FastAPI webhook (thin) |
| `scripts/` | one helper per setup step |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env           # then fill it in
```

## Run the steps in order

Each one must pass before the next is worth trying.

```bash
python scripts/get_chat_id.py     # -> paste into ALLOWED_CHAT_IDS
python scripts/list_models.py     # -> paste a real id into GEMINI_MODEL
python scripts/check_notion.py    # -> integration sees the DB, schema matches
python scripts/test_extract.py    # -> LLM parses samples, writes nothing
python pipeline.py "chai 40"      # -> a real row appears in Notion
```

Then the server:

```bash
uvicorn main:app --reload
python scripts/fake_update.py "uber 250"    # in a second terminal
```

## Deploy

```bash
gcloud run deploy expense-bot --source . --region asia-south1 --allow-unauthenticated
gcloud run services update expense-bot --region asia-south1 \
  --set-env-vars "TELEGRAM_BOT_TOKEN=..,TELEGRAM_WEBHOOK_SECRET=..,ALLOWED_CHAT_IDS=..,NOTION_API_KEY=..,NOTION_DATABASE_ID=..,GEMINI_API_KEY=..,GEMINI_MODEL=..,TIMEZONE=Asia/Kolkata"

python scripts/set_webhook.py https://<your-cloud-run-url>
python scripts/set_webhook.py --info     # last_error_message should be empty
```

`--allow-unauthenticated` is required because Telegram cannot authenticate to
GCP. `TELEGRAM_WEBHOOK_SECRET` is what actually guards the endpoint.

## Notes

- `.env` is gitignored and gcloudignored. If a token ever reaches a commit,
  rotate it (`/revoke` in BotFather, regenerate the Notion key) - deleting it
  in a later commit does not help.
- The webhook always returns 200. A non-200 makes Telegram retry forever.
- Duplicate suppression is in-memory, so a cold start can allow one repeat row.
