# ─────────────────────────────────────────────────────────────────────────────
#  Researcher KB Pipeline — Cloud Run Job
#  Entrypoint: python pipeline.py --stage 4
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Keeps Python from buffering stdout/stderr (critical for Cloud Run log capture)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# curl is useful for health probes / debugging; ca-certificates keeps TLS happy
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer separately from code
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# ── Application source ────────────────────────────────────────────────────────
# Only copy the pipeline package; local data/ is NOT baked into the image
# (Cloud Run Jobs write to /app/data at runtime or to Cloud Storage)
COPY researcher-kb-pipeline/ /app/

# ─────────────────────────────────────────────────────────────────────────────
#  Runtime
#  All secrets/config come from Cloud Run Job environment variables:
#    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
#    PINECONE_API_KEY, PINECONE_INDEX (optional, defaults to researcher-kb-index)
#    GOOGLE_CLOUD_PROJECT (required by Vertex AI SDK)
#  ADC is provided automatically by the Cloud Run service account.
# ─────────────────────────────────────────────────────────────────────────────
ENTRYPOINT ["python", "pipeline.py"]
