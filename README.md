# AI Researcher Ranking System

An end-to-end system that identifies and ranks researchers for a topic using semantic search plus a custom scoring pipeline.

Built for a practical use case: helping teams find relevant academic experts for collaboration, hiring, and research partnerships.

## What Problem This Solves

Citation-heavy discovery tools often return famous researchers who are not the best match for a specific query.

This system optimizes for both:

1. Query relevance to current need
2. Research impact signal for credibility

Result: a ranked list that is more useful for decision-making than citation-only sorting.

## What The System Does

Given a query like "quantum computing" or "robotics", the system:

1. Retrieves semantically relevant papers from Pinecone
2. Maps those papers to researchers
3. Computes per-researcher relevance score (Q)
4. Computes per-researcher impact score (H)
5. Produces an explainable final ranking with top supporting papers

## End-to-End Architecture

The platform has two production-oriented phases.

### Phase 1: Data and Knowledge Base Pipeline

Pipeline location: [researcher-kb-pipeline](researcher-kb-pipeline)

1. Discover papers from OpenAlex by topic/query
2. Extract and deduplicate researchers
3. Enrich profiles with metrics, collaborators, and institution context
4. Assemble final researcher knowledge base artifacts

Primary artifacts:

- [researcher-kb-pipeline/data/knowledge_base.json](researcher-kb-pipeline/data/knowledge_base.json)
- [researcher-kb-pipeline/data/knowledge_base_summary_schema.json](researcher-kb-pipeline/data/knowledge_base_summary_schema.json)

### Phase 2: Online Ranking API

Service entrypoint: [researcher-kb-pipeline/rank_service.py](researcher-kb-pipeline/rank_service.py)

- `POST /rank` returns ranked researchers and scoring breakdown
- `GET /health` verifies service liveness

Ranking and query logic:

- [researcher-kb-pipeline/search.py](researcher-kb-pipeline/search.py)
- [researcher-kb-pipeline/ranking.py](researcher-kb-pipeline/ranking.py)

## Scoring Model

The default mode is intentionally simple and explainable.

### Q Score (Relevance)

Average similarity of top 20 matched papers per researcher (zero-padded if fewer than 20 matches).

```text
Q = avg(top 20 paper similarity scores)
```

### H Score (Impact)

Normalized h-index cap.

```text
H = min(h_index / 100, 1.0)
```

### Final Score

Weighted combination of relevance and impact.

```text
Final = wQ * Q + wH * H
```

Default weights are controlled in [researcher-kb-pipeline/config.py](researcher-kb-pipeline/config.py) (`Q_WEIGHT`, `H_WEIGHT`, both default to `0.5`).

## Tech Stack

Backend:

- Python
- FastAPI

Data and retrieval:

- OpenAlex
- Semantic Scholar
- MySQL (structured records)
- Pinecone (vector retrieval)

Infrastructure:

- Docker
- Google Cloud Run

## Local Setup

### Prerequisites

- Python 3.11+
- pip
- Optional: Docker
- Optional: gcloud CLI

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

# Optional depending on embedding configuration
export OPENAI_API_KEY="<openai-api-key>"
```

## Run The System

### Run Phase 1 Pipeline

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

### Run Phase 2 Ranking API

```bash
cd researcher-kb-pipeline
uvicorn rank_service:app --host 0.0.0.0 --port 8080
```

### Test API

```bash
curl -s -X POST "http://127.0.0.1:8080/rank" \
  -H "Content-Type: application/json" \
  -d '{"query":"quantum computing","use_mock_data":true,"limit":10}'
```

## API Contract

### `POST /rank` request example

```json
{
  "query": "quantum computing",
  "limit": 10
}
```

Response includes:

- Ranked researchers
- `Q`, `H`, and `final_score`
- Reason summary and top supporting papers

## Deployment Setup (High-Level)

### Build ingestion job image

```bash
gcloud builds submit . \
  --tag us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/researcher-repo/researcher-ingestion
```

### Build ranking service image

```bash
gcloud builds submit . \
  --config cloudbuild.rank.yaml \
  --project <YOUR_GCP_PROJECT_ID>
```

### Deploy ranking service

```bash
gcloud run deploy researcher-ranking \
  --image us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/researcher-repo/researcher-ranking:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

Add Cloud SQL and Secret Manager bindings for your environment.

## Design Decisions and Tradeoffs

1. Prioritize relevance first, not just fame
2. Keep scoring explainable for stakeholder trust
3. Use configurable weights so product behavior can be tuned
4. Maintain a simple default mode and an advanced weighted mode for experimentation

## Current Focus

1. Improving ranking quality and evaluation metrics
2. Handling sparse-profile and noisy-match edge cases
3. Expanding benchmarking across more query categories

## Repository Guide

- [researcher-kb-pipeline/pipeline.py](researcher-kb-pipeline/pipeline.py): stage orchestrator
- [researcher-kb-pipeline/stage1_discover.py](researcher-kb-pipeline/stage1_discover.py): paper discovery
- [researcher-kb-pipeline/stage2_extract.py](researcher-kb-pipeline/stage2_extract.py): researcher extraction
- [researcher-kb-pipeline/stage3_enrich.py](researcher-kb-pipeline/stage3_enrich.py): profile enrichment
- [researcher-kb-pipeline/stage4_assemble.py](researcher-kb-pipeline/stage4_assemble.py): final assembly
- [researcher-kb-pipeline/search.py](researcher-kb-pipeline/search.py): retrieval and ranking integration
- [researcher-kb-pipeline/ranking.py](researcher-kb-pipeline/ranking.py): scoring functions
- [researcher-kb-pipeline/rank_service.py](researcher-kb-pipeline/rank_service.py): FastAPI service

## Notes

- This README is environment-agnostic.
- No real project IDs, service account emails, or secret values are stored here.
