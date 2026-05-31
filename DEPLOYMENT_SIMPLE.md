# Frontend Deployment — Cloud Run Quick Reference

Deploy the `research-ai` frontend to Google Cloud Run and connect it to the
existing `researcher-ranking` backend.

---

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Cloud Build, Artifact Registry, and Cloud Run APIs enabled on the project
- Artifact Registry repo `researcher-repo` exists in `us-central1`

```bash
# One-time: enable APIs if not already done
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project=project-d84d7c5a-c91d-497b-b78
```

---

## 1. Deploy the Frontend

Run from the **repo root** (not from inside `Lam-research/`):

```bash
gcloud builds submit . \
  --config cloudbuild.frontend.yaml \
  --project project-d84d7c5a-c91d-497b-b78
```

`cloudbuild.frontend.yaml` already contains:

- `_RANKING_API_URL=https://researcher-ranking-843231871344.us-central1.run.app`
- `_RANKING_API_AUTH_TOKEN=""` (no auth token — backend is public)
- `--allow-unauthenticated` (frontend is publicly accessible)
- `--port=8080` (matches the port Cloud Run injects via the `PORT` env var)

---

## 2. Get the Frontend URL

```bash
gcloud run services describe research-ai \
  --region us-central1 \
  --project project-d84d7c5a-c91d-497b-b78 \
  --format "value(status.url)"
```

Save it for the test commands below:

```bash
export FRONTEND_URL=$(gcloud run services describe research-ai \
  --region us-central1 \
  --project project-d84d7c5a-c91d-497b-b78 \
  --format "value(status.url)")

export BACKEND_URL="https://researcher-ranking-843231871344.us-central1.run.app"
```

---

## 3. Test Backend Health (direct)

Verifies the existing Python ranking service is up independently of the frontend.

```bash
curl -s "$BACKEND_URL/health" | python3 -m json.tool
```

Expected response:

```json
{
  "status": "ok",
  "service": "ranking"
}
```

---

## 4. Test Frontend Health (direct)

Verifies the Node.js / Express frontend container started correctly.

```bash
curl -s "$FRONTEND_URL/health" | python3 -m json.tool
```

Expected response:

```json
{
  "ok": true,
  "service": "research-ai"
}
```

---

## 5. Test Frontend → Backend Health Proxy

Verifies the frontend's Express proxy can reach the backend.

```bash
curl -s "$FRONTEND_URL/api/ranking/health" | python3 -m json.tool
```

Expected response:

```json
{
  "ok": true,
  "upstreamStatus": 200,
  "service": "ranking",
  "data": {
    "status": "ok",
    "service": "ranking"
  }
}
```

---

## 6. Test Frontend → Backend Ranking Call

### 6a. Mock data (no database or Pinecone required)

Use this first to verify end-to-end request plumbing without needing a live DB.

```bash
curl -s -X POST "$FRONTEND_URL/api/ranking/rank" \
  -H "Content-Type: application/json" \
  -d '{"query": "semiconductor devices", "use_mock_data": true, "limit": 3}' \
  | python3 -m json.tool
```

### 6b. Live data (requires DB + Pinecone connected and seeded)

```bash
curl -s -X POST "$FRONTEND_URL/api/ranking/rank" \
  -H "Content-Type: application/json" \
  -d '{"query": "semiconductor devices", "limit": 5}' \
  | python3 -m json.tool
```

Expected response shape:

```json
{
    "results": [...],
    "pareto": [...],
    "debug": {
        "filters": {},
        "ranked_count": 5
    }
}
```

---

## Route Map (for reference)

| Frontend route            | Backend route | Notes                                        |
| ------------------------- | ------------- | -------------------------------------------- |
| `GET /api/ranking/health` | `GET /health` | Proxied by Express                           |
| `POST /api/ranking/rank`  | `POST /rank`  | Proxied + request normalized by Express      |
| `GET /health`             | —             | Handled by Express directly                  |
| `GET /api/auth/*`         | —             | Handled by Express directly (MySQL sessions) |

The frontend proxy lives in `Lam-research/server/ranking.ts`.  
It normalizes the request (maps `citation_start_year` → `start_year`, etc.)  
before forwarding to `RANKING_API_URL`.

---

## 7. Cloud SQL (MySQL) Setup

Auth, sessions, and per-user AI settings are stored in Cloud SQL MySQL instead
of the local flat-file `data/app-data.json`.

### 7a. Create a Cloud SQL instance (one-time)

```bash
gcloud sql instances create research-ai-db \
  --database-version=MYSQL_8_0 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --project=project-d84d7c5a-c91d-497b-b78
```

### 7b. Create the database and user

```bash
# Create the database
gcloud sql databases create research_ai \
  --instance=research-ai-db \
  --project=project-d84d7c5a-c91d-497b-b78

# Create a dedicated app user (replace <PASSWORD> with a strong password)
gcloud sql users create research_ai \
  --instance=research-ai-db \
  --password=<PASSWORD> \
  --project=project-d84d7c5a-c91d-497b-b78
```

### 7c. Schema — automatic on startup

`initDb()` runs on every server start and issues `CREATE TABLE IF NOT EXISTS`
for all five tables (`users`, `sessions`, `verification_codes`,
`user_ai_settings`, `saved_researchers`). No manual migration script is needed.

### 7d. Local development with the Cloud SQL proxy

```bash
# Install the proxy binary (already in bin/cloud-sql-proxy)
# Start it (listens on 127.0.0.1:3306 by default):
./bin/cloud-sql-proxy \
  project-d84d7c5a-c91d-497b-b78:us-central1:research-ai-db \
  --port 3306
```

Then in your `.env` (copy from `.env.example`):

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=research_ai
DB_PASSWORD=<PASSWORD>
DB_NAME=research_ai
```

### 7e. Deploy to Cloud Run with Cloud SQL

Pass DB credentials and the Cloud SQL instance connection name to the build
trigger substitutions, or supply them on the CLI:

```bash
gcloud builds submit . \
  --config cloudbuild.frontend.yaml \
  --project project-d84d7c5a-c91d-497b-b78 \
  --substitutions \
    _DB_HOST=/cloudsql/project-d84d7c5a-c91d-497b-b78:us-central1:research-ai-db,\
    _DB_USER=research_ai,\
    _DB_PASSWORD=<PASSWORD>,\
    _DB_NAME=research_ai,\
    _AI_SETTINGS_ENCRYPTION_KEY=<64-hex-chars>,\
    _CLOUD_SQL_INSTANCE=project-d84d7c5a-c91d-497b-b78:us-central1:research-ai-db
```

`_DB_HOST` must start with `/cloudsql/` so the server uses the Unix socket
instead of a TCP connection.

### 7f. Generate an encryption key

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Store the output as `_AI_SETTINGS_ENCRYPTION_KEY` in the Cloud Build trigger
substitutions (or as a Cloud Run environment variable). Keep it secret — it is
used to AES-256-GCM-encrypt stored API keys.

### 7g. Grant Cloud Run service account Cloud SQL access

```bash
# Find the Cloud Run service account (usually <project-number>-compute@...)
PROJECT_NUMBER=$(gcloud projects describe project-d84d7c5a-c91d-497b-b78 \
  --format="value(projectNumber)")

gcloud projects add-iam-policy-binding project-d84d7c5a-c91d-497b-b78 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

### 7h. Restore `--frozen-lockfile` after regenerating the lockfile

After adding `mysql2` to `package.json`, run locally:

```bash
cd Lam-research && pnpm install
```

Then commit the updated `pnpm-lock.yaml` and restore the Dockerfile line:

```dockerfile
RUN pnpm install --frozen-lockfile
```
