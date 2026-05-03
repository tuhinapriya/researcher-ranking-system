# Researcher Ranking System

A two-part system for finding and ranking researchers for a topic.

## 1. Project Summary

This project does two things:

1. Builds a researcher knowledge base from public scholarly sources.
2. Ranks researchers for a user query using semantic relevance and profile strength.

In short: it helps answer questions like "Who are the strongest researchers in quantum computing for this query?"

## 2. Core Idea

Most APIs give raw papers or raw profiles. This system combines both:

- Researcher profile signals (h-index, citations, institution quality, seniority)
- Query relevance signals (paper-level semantic match to user query)

Then it produces ranked results with reasons.

## 3. How It Works

### Phase 1: Build the Knowledge Base (Batch Pipeline)

The pipeline in [researcher-kb-pipeline](researcher-kb-pipeline) runs in stages:

1. Discover papers from OpenAlex by topic/query
2. Extract and deduplicate researchers
3. Enrich researcher + institution + collaborator data
4. Assemble final structured outputs

Main outputs:

- [researcher-kb-pipeline/data/knowledge_base.json](researcher-kb-pipeline/data/knowledge_base.json)
- [researcher-kb-pipeline/data/knowledge_base_summary_schema.json](researcher-kb-pipeline/data/knowledge_base_summary_schema.json)

### Phase 2: Serve Rankings (Online API)

The ranking service accepts a query and returns top researchers with explanation fields:

- Endpoint: POST /rank
- Health check: GET /health
- App file: [researcher-kb-pipeline/rank_service.py](researcher-kb-pipeline/rank_service.py)

## 4. Repository Layout

- [researcher-kb-pipeline/pipeline.py](researcher-kb-pipeline/pipeline.py): stage orchestrator
- [researcher-kb-pipeline/stage1_discover.py](researcher-kb-pipeline/stage1_discover.py): paper discovery
- [researcher-kb-pipeline/stage2_extract.py](researcher-kb-pipeline/stage2_extract.py): author extraction
- [researcher-kb-pipeline/stage3_enrich.py](researcher-kb-pipeline/stage3_enrich.py): enrichment
- [researcher-kb-pipeline/stage4_assemble.py](researcher-kb-pipeline/stage4_assemble.py): assembly
- [researcher-kb-pipeline/search.py](researcher-kb-pipeline/search.py): ranking/search logic
- [researcher-kb-pipeline/rank_service.py](researcher-kb-pipeline/rank_service.py): FastAPI service

## 5. Local Setup

### Prerequisites

- Python 3.11+
- pip
- Optional: Docker (for containerized runs)
- Optional: gcloud CLI (for Cloud Run deployment)

### Install

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ranking.txt
```

### Environment Variables

Set these for real ranking (non-mock):

```bash
export DB_HOST="<db-host-or-cloudsql-socket>"
export DB_USER="<db-user>"
export DB_PASSWORD="<db-password>"
export DB_NAME="<db-name>"
export DB_PORT="3306"

export PINECONE_API_KEY="<pinecone-api-key>"
export PINECONE_INDEX="researcher-papers"

# Optional if using OpenAI embeddings in your flow
export OPENAI_API_KEY="<openai-api-key>"
```

## 6. Run Locally

### Run Phase 1 (Pipeline)

```bash
cd researcher-kb-pipeline
python pipeline.py --limit 10
```

Useful variants:

```bash
python pipeline.py
python pipeline.py --stage 1
python pipeline.py --stage 3a --force
```

### Run Phase 2 (Ranking API)

```bash
cd researcher-kb-pipeline
uvicorn rank_service:app --host 0.0.0.0 --port 8080
```

Test API:

```bash
curl -s -X POST "http://127.0.0.1:8080/rank" \
  -H "Content-Type: application/json" \
  -d '{"query":"quantum computing","use_mock_data":true,"limit":25}'
```

## 7. Deploy Setup (Cloud, High-Level)

### Ingestion Job Image

```bash
gcloud builds submit . \
  --tag us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/researcher-repo/researcher-ingestion
```

### Ranking Service Image

```bash
gcloud builds submit . \
  --config cloudbuild.rank.yaml \
  --project <YOUR_GCP_PROJECT_ID>
```

### Deploy Ranking Service

```bash
gcloud run deploy researcher-ranking \
  --image us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/researcher-repo/researcher-ranking:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

Add Cloud SQL and Secret Manager bindings as needed for your environment.

## 8. Typical Usage Flow

1. Run Phase 1 pipeline to refresh researcher data.
2. Ensure database/vector index is populated.
3. Run Phase 2 API.
4. Send query to /rank and consume ranked results.

## 9. Notes

- This README is setup-first and environment-agnostic.
- No real project IDs, service account emails, or secret values are stored here.
