# Telegram -> Notion expense tracker

Send `chai 40` to a Telegram bot; Amazon Bedrock parses it; a row appears in
Notion.

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
| `extractor.py` | message -> `Expense` via Bedrock forced tool call |
| `pipeline.py` | glue; runnable standalone for testing |
| `telegram_api.py` | sendMessage |
| `main.py` | FastAPI webhook (thin) |
| `scripts/` | one helper per setup step |

## AWS setup

1. In the **Bedrock console -> Model access**, enable the model you want.
   Listing a model and having access to it are separate things.
2. Create an IAM principal that can call it. Minimum policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel"],
    "Resource": "*"
  }, {
    "Effect": "Allow",
    "Action": ["bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"],
    "Resource": "*"
  }]
}
```

Narrow `Resource` to the model ARN once you have picked one.

3. Credentials are read by boto3 from the standard chain. Locally use
   `aws configure` or `AWS_PROFILE`. On Cloud Run there is no AWS role, so
   static keys go in the service's env vars - scope that IAM user to the two
   actions above and nothing else.

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
python scripts/list_models.py     # -> paste a real id into BEDROCK_MODEL_ID
python scripts/check_notion.py    # -> integration sees the DB, schema matches
python scripts/test_extract.py    # -> Bedrock parses samples, writes nothing
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
  --set-env-vars "TELEGRAM_BOT_TOKEN=..,TELEGRAM_WEBHOOK_SECRET=..,ALLOWED_CHAT_IDS=..,NOTION_API_KEY=..,NOTION_DATABASE_ID=..,AWS_REGION=us-east-1,BEDROCK_MODEL_ID=..,AWS_ACCESS_KEY_ID=..,AWS_SECRET_ACCESS_KEY=..,TIMEZONE=Asia/Kolkata"

python scripts/set_webhook.py https://<your-cloud-run-url>
python scripts/set_webhook.py --info     # last_error_message should be empty
```

`--allow-unauthenticated` is required because Telegram cannot authenticate to
GCP. `TELEGRAM_WEBHOOK_SECRET` is what actually guards the endpoint.

If the long-lived AWS key bothers you, deploying on AWS instead (App Runner,
or Lambda + Function URL) lets an execution role replace it.

## Notes

- `NOTION_DATABASE_ID` accepts a bare id, a dashed UUID, or the full database
  URL. The `?v=` part is the view id and is ignored.
- `.env` is gitignored. If a credential ever reaches a
  commit, rotate it - deleting it in a later commit does not help.
- The webhook always returns 200. A non-200 makes Telegram retry forever.
- Duplicate suppression is in-memory, so a cold start can allow one repeat row.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| Notion 404 "object not found" | Integration not added under the database's **Connections** |
| `AccessDeniedException` | IAM missing `bedrock:InvokeModel`, **or** model access not enabled in the console |
| "inference profile" / "on-demand throughput isn't supported" | Use the `us.`-prefixed inference profile id from `list_models.py` |
| `get_chat_id.py` prints nothing | A webhook is set; run `set_webhook.py --delete` first |
| `ZoneInfo` KeyError on Windows | `pip install tzdata` |
