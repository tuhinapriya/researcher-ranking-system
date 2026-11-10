#!/usr/bin/env bash
set -euo pipefail

# Simple pre-deploy check to ensure required secrets exist in Secret Manager
# and to fail the build early with a clear message if something is missing.

REQUIRED_SECRETS=("pinecone-key" "db-password")
MISSING=()
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

echo "Running pre-deploy checks for required secrets..."
if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" = "(unset)" ] || [ "${PROJECT_ID}" = "None" ]; then
  echo "ERROR: PROJECT_ID is not set and no default gcloud project is configured."
  exit 1
fi

for s in "${REQUIRED_SECRETS[@]}"; do
  if ! gcloud secrets describe "$s" --project="$PROJECT_ID" --format="value(name)" >/dev/null 2>&1; then
    echo "ERROR: required secret '$s' not found in Secret Manager"
    MISSING+=("$s")
  else
    echo "OK: secret '$s' exists"
  fi
done

if [ ${#MISSING[@]} -ne 0 ]; then
  echo ""
  echo "One or more required secrets are missing: ${MISSING[*]}"
  echo "Please create them in Secret Manager before deploying. Example:"
  echo "  echo -n \"<value>\" | gcloud secrets create pinecone-key --data-file=- --replication-policy=automatic"
  exit 1
fi

echo "Pre-deploy checks passed."
