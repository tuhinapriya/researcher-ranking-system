# AI Researcher Ranking System

An end-to-end system that identifies and ranks researchers for a topic using semantic search plus a custom scoring pipeline.

Built for a practical use case: helping teams find relevant academic experts for collaboration, hiring, and research partnerships.

## What Problem This Solves

Citation-heavy discovery tools often return famous researchers who are not the best match for a specific query.

This system optimizes for both:

1. Query relevance to current need (Q score)
2. Research impact signal for credibility (R score — citation-window based)

Result: a ranked list that is more useful for decision-making than citation-only sorting.

---

## Production Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Cloud Run: research-ai                          │
│                                                                          │
│   React SPA (Vite)        Express Server (Node.js)                       │
│   ─────────────────  ──>  ────────────────────────                       │
│   Lam-research/client     Lam-research/server/                           │
│                                                                          │
│   Static file serving:                                                   │
│     GET /*  → serves index.html                                          │
│                                                                          │
│   Internal API routes:                                                   │
│     POST /api/auth/*          → session auth (flat-file store)           │
│     GET/PUT /api/saved-*      → per-user saved researcher lists          │
│     POST /api/ai/chat         → BYOK AI proxy (user-supplied key)        │
│                                                                          │
│   Proxy routes → ranking service:                                        │
│     GET  /api/ranking/health  → GET  /health                             │
│     POST /api/ranking/rank    → POST /rank                               │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ server-side HTTP (RANKING_API_URL)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Cloud Run: researcher-ranking                       │
│                                                                          │
│   FastAPI (Python)           rank_service.py                             │
│                                                                          │
│   GET  /health                                                           │
│   POST /rank                                                             │
│         ↓                                                                │
│   search.py → ranking.py                                                 │
│         ↓              ↓                                                 │
│   Pinecone          MySQL (Cloud SQL)                                    │
│   (vector search)   (researcher profiles + paper metadata)               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Two-service design rationale

| Service              | Stack             | Responsibility                                                                     |
| -------------------- | ----------------- | ---------------------------------------------------------------------------------- |
| `research-ai`        | Node.js / Express | Serves the React SPA; proxies ranking requests; handles auth and saved researchers |
| `researcher-ranking` | Python / FastAPI  | Ranking source of truth; Pinecone vector search; MySQL filtering; Q/R scoring      |

The browser never calls the Python service directly — all ranking traffic goes through the Express proxy. This keeps database credentials and Pinecone keys confined to the Python service environment.

---

## Scoring Model

### Q Score (Query Relevance)

Average cosine similarity of the top-20 matched papers per researcher (zero-padded when fewer than 20 match).

```text
Q_raw = avg(top-20 paper similarity scores, zero-padded)
Q_norm = min-max normalization of Q_raw within the returned result set
```

### R Score (Research Impact)

Total citations received by query-matched papers **within the selected citation year window**.

```text
R_raw = sum(citations for matched papers where year in [start_year, end_year])
R_norm = min-max normalization of log(1 + R_raw) within the returned result set
```

### Final Score

```text
Final = (wQ * Q_norm + wR * R_norm) / (wQ + wR)
```

Default weights: `wQ = 0.7`, `wR = 0.3` (configurable via the UI sliders or request body).

H-index is exposed as **profile context only** — it does not affect the default ranking.

---

## Search Modes

| UI Mode        | Frontend sends               | Backend behavior                                            |
| -------------- | ---------------------------- | ----------------------------------------------------------- |
| Auto (Default) | `query`                      | Semantic search on all researchers                          |
| Name           | `query` + `author_name`      | Semantic search → filter results by researcher name (LIKE)  |
| Institution    | `query` + `institution_name` | Semantic search → filter results by institution name (LIKE) |
| Query (Topic)  | `query`                      | Semantic search on all researchers                          |

---

## Tech Stack

**Frontend (`Lam-research/`)**

- React 19 + TypeScript
- Vite (build) + Express (prod server + proxy)
- Tailwind CSS + Radix UI

**Backend (`researcher-kb-pipeline/`)**

- Python 3.11
- FastAPI + uvicorn
- Pinecone (vector retrieval)
- MySQL via `mysql-connector-python` (Cloud SQL compatible)
- Vertex AI / Google Cloud AI Platform (embeddings)

**Infrastructure**

- Google Cloud Run (two services)
- Google Artifact Registry (Docker images)
- Cloud Build (CI/CD via `cloudbuild.rank.yaml` and `cloudbuild.frontend.yaml`)

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 22+ and pnpm
- Docker (optional)
- gcloud CLI (optional, for Cloud SQL proxy)

### Backend Ranking Service

```bash
# From repo root
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-ranking.txt

# Copy and fill in environment variables
cp researcher-kb-pipeline/.env.example researcher-kb-pipeline/.env
# Edit .env with your DB and Pinecone credentials

# Run with mock data (no DB or Pinecone required)
cd researcher-kb-pipeline
uvicorn rank_service:app --host 0.0.0.0 --port 8080

# Test (mock data mode — no credentials needed)
curl -s -X POST http://localhost:8080/rank \
  -H "Content-Type: application/json" \
  -d '{"query":"quantum computing","use_mock_data":true,"limit":10}' | python3 -m json.tool
```

### Frontend App

```bash
cd Lam-research

# Install dependencies
pnpm install

# Copy and fill in environment variables
cp .env.example .env
# Set RANKING_API_URL=http://localhost:8080 for local backend

# Development server (hot reload, proxy wired via vite.config.ts)
pnpm dev
# Open http://localhost:3000
```

### Run the Full ETL Pipeline (optional)

```bash
cd researcher-kb-pipeline
# Requires full .env with DB + Pinecone + Google Cloud credentials

python pipeline.py --stage 1          # Discover papers
python pipeline.py --stage 2          # Extract researchers
python pipeline.py --stage 3a         # Enrich profiles
python pipeline.py --stage 4          # Assemble + upsert to DB and Pinecone
python pipeline.py                    # All stages (full run)
```

---

## API Contract

### `POST /rank` request

```json
{
  "query": "quantum computing",
  "author_name": "Letaief",
  "institution_name": null,
  "region": null,
  "institution_id": null,
  "start_year": 2020,
  "end_year": 2025,
  "q_weight": 0.7,
  "r_weight": 0.3,
  "limit": 30,
  "use_mock_data": false
}
```

### `POST /rank` response

```json
{
  "results": [
    {
      "researcher_id": "A1234567890",
      "name": "Jane Smith",
      "institution": "MIT",
      "region": "North America",
      "Q": 0.85,
      "R": 0.62,
      "final_score": 0.78,
      "reason": {
        "primary_driver": "quantum algorithms",
        "summary": "Strong match on quantum circuit optimization papers.",
        "highlights": ["quantum error correction", "variational circuits"],
        "top_papers": [
          { "paper_id": "10.1234/...", "title": "...", "year": 2023, "similarity": 0.91 }
        ]
      },
      "contribution": {
        "matched_paper_count": 8,
        "top_paper_share": 0.23,
        "top_3_paper_share": 0.55,
        "top_5_paper_share": 0.72,
        "paper_contributions": [...]
      },
      "components": {
        "R_raw": 412,
        "matched_paper_count": 8
      }
    }
  ],
  "pareto": { "enabled": false, "dominated_ids": [], "dominated_by": {} },
  "debug": { ... }
}
```

---

## Cloud Run Deployment

### Deploy the Ranking Backend

```bash
gcloud builds submit . \
  --config cloudbuild.rank.yaml \
  --project <YOUR_GCP_PROJECT_ID>
```

Then set required environment variables on the Cloud Run service:

```bash
gcloud run services update researcher-ranking \
  --region us-central1 \
  --set-env-vars \
    DB_HOST=/cloudsql/<PROJECT>:<REGION>:<INSTANCE>,\
    DB_USER=<user>,\
    DB_PASSWORD=<password>,\
    DB_NAME=<dbname>,\
    PINECONE_API_KEY=<key>,\
    PINECONE_INDEX=researcher-kb-index,\
    GOOGLE_CLOUD_PROJECT=<project>
```

Add Cloud SQL instance connection:

```bash
gcloud run services update researcher-ranking \
  --region us-central1 \
  --add-cloudsql-instances <PROJECT>:<REGION>:<INSTANCE>
```

### Deploy the Frontend

```bash
gcloud builds submit . \
  --config cloudbuild.frontend.yaml \
  --project <YOUR_GCP_PROJECT_ID> \
  --substitutions _RANKING_API_URL=https://researcher-ranking-<hash>-uc.a.run.app
```

### Verify Both Services

```bash
# Backend health
curl https://researcher-ranking-<hash>-uc.a.run.app/health

# Frontend health
curl https://research-ai-<hash>-uc.a.run.app/health

# End-to-end ranking via frontend proxy
curl -s -X POST https://research-ai-<hash>-uc.a.run.app/api/ranking/rank \
  -H "Content-Type: application/json" \
  -d '{"query":"semiconductor devices","limit":5}' | python3 -m json.tool
```

---

## Repository Guide

```
Practicum/
├── Lam-research/                   # Frontend React SPA + Express server
│   ├── client/src/                 # React app (pages, components, types)
│   ├── server/                     # Express server
│   │   ├── index.ts                # Route registration + static serving
│   │   ├── ranking.ts              # Ranking proxy (normalizes + forwards to backend)
│   │   ├── auth.ts                 # Session auth (cookie + flat-file store)
│   │   └── ai.ts                   # BYOK AI proxy
│   ├── Dockerfile                  # Multi-stage Node.js build
│   ├── .env.example                # Frontend env vars
│   └── render.yaml                 # Render.com deployment (alternative)
│
├── researcher-kb-pipeline/         # Backend ranking service + ETL pipeline
│   ├── rank_service.py             # FastAPI app — primary production entrypoint
│   ├── api.py                      # Alternate FastAPI app (simpler, no response models)
│   ├── search.py                   # Orchestrates Pinecone search + DB filtering + ranking
│   ├── ranking.py                  # Q/R/final_score computation and Pareto logic
│   ├── db.py                       # MySQL connection + all SQL queries
│   ├── embeddings.py               # Vertex AI / embedding provider wrapper
│   ├── pinecone_client.py          # Pinecone index client
│   ├── config.py                   # Pipeline + ranking configuration constants
│   ├── pipeline.py                 # ETL stage orchestrator (offline data ingestion)
│   ├── stage1_discover.py          # OpenAlex paper discovery
│   ├── stage2_extract.py           # Researcher extraction from papers
│   ├── stage3_enrich.py            # Profile enrichment (h-index, co-authors, etc.)
│   ├── stage4_assemble.py          # Final assembly + MySQL + Pinecone upsert
│   ├── schema.sql                  # MySQL DDL
│   └── .env.example                # Backend env vars
│
├── Dockerfile                      # ETL pipeline image (pipeline.py entrypoint)
├── Dockerfile.api                  # Full API image (api.py, requires all deps)
├── Dockerfile.rank                 # Ranking-only image (rank_service.py, minimal deps)
├── cloudbuild.rank.yaml            # Cloud Build: build + deploy researcher-ranking
├── cloudbuild.frontend.yaml        # Cloud Build: build + deploy research-ai
├── requirements.txt                # Full pipeline Python dependencies
├── requirements-ranking.txt        # Minimal ranking service Python dependencies
└── README.md                       # This file
```

---

## Known Limitations

1. **Author name search is approximate**: The `author_name` filter uses a SQL LIKE query against the DB. It works well for unique last names but may return multiple researchers for common names. The semantic query is still the name string, so Q scores for author searches may be lower than for topic searches.

2. **Auth uses a flat JSON file**: User sessions and saved researchers are stored in `data/app-data.json` inside the container. This is **ephemeral in Cloud Run** — data is lost on container restart or scale-out. For production, replace with a Cloud SQL table or Cloud Firestore.

3. **Institution search requires institution to be in the DB**: The `institution_name` LIKE filter only matches researchers whose `current_institution_id` links to a record in the `institutions` table. Researchers with missing institution data will be excluded.

4. **Embeddings require Vertex AI or compatible provider**: The ranking service computes query embeddings at request time. Ensure the Cloud Run service account has `roles/aiplatform.user` or that `GOOGLE_CLOUD_PROJECT` is set correctly.

---

## Design Decisions

1. **Frontend is a thin display layer** — no ranking logic, no score normalization, no filtering. The backend is the single source of truth.
2. **Two-service split** — keeps Python dependencies (Pinecone SDK, Vertex AI, mysql-connector) out of the Node.js container, and keeps Node.js/npm build complexity out of the Python service.
3. **Proxy pattern** — the Express server proxies ranking calls server-side, keeping database and Pinecone credentials out of the browser and out of the frontend container.
4. **Configurable weights** — `q_weight` and `r_weight` are passed per-request so the frontend sliders directly control ranking without requiring a backend redeploy.
5. **Mock data fallback** — `use_mock_data: true` allows the ranking service to run without a live database or Pinecone index, useful for UI development and demos.
