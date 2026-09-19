"""Print Bedrock model ids your account can actually invoke in this region.

Newer models cannot be called by their raw foundation-model id - they need a
cross-region inference profile id (same id with a 'us.' / 'eu.' / 'apac.'
prefix). Both lists are printed; prefer an inference profile if one exists.
"""
import _bootstrap  # noqa: F401
import boto3
from botocore.exceptions import ClientError

import config

bedrock = boto3.client("bedrock", region_name=config.AWS_REGION)

print(f"Region: {config.AWS_REGION}\n")

print("Foundation models (TEXT output, on-demand):")
try:
    models = bedrock.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
    for model in models:
        if "ON_DEMAND" not in model.get("inferenceTypesSupported", []):
            continue
        print(f"  {model['modelId']}")
except ClientError as exc:
    print(f"  could not list: {exc}")

print("\nInference profiles (use these ids for newer models):")
try:
    profiles = bedrock.list_inference_profiles()["inferenceProfileSummaries"]
    if not profiles:
        print("  (none)")
    for profile in profiles:
        print(f"  {profile['inferenceProfileId']}")
except ClientError as exc:
    print(f"  could not list: {exc}")

print(f"\nCurrently configured: BEDROCK_MODEL_ID={config.BEDROCK_MODEL_ID}")
print(
    "\nIf a model is listed but invoking it returns AccessDenied, enable it on "
    "the Bedrock console's 'Model access' page - listing and access are separate."
)
