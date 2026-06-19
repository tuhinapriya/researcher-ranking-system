#!/usr/bin/env bash
set -euo pipefail

# Simple pre-deploy check to ensure required secrets exist in Secret Manager
# and to fail the build early with a clear message if something is missing.

REQUIRED_SECRETS=("pinecone-key" "db-password")
MISSING=()

echo "Running pre-deploy checks for required secrets..."
for s in "${REQUIRED_SECRETS[@]}"; do
  if ! gcloud secrets describe "$s" --format="value(name)" >/dev/null 2>&1; then
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
