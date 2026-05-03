# Researcher Backend Deployment Guide

This guide explains how to rebuild the container image, update the existing Cloud Run job, and execute the researcher ingestion pipeline.

## Project Details

- **Project ID:** project-d84d7c5a-c91d-497b-b78
- **Region:** us-central1
- **Existing Cloud Run Job:** researcher-ingestion
- **Artifact Registry Image:** us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ingestion
- **Cloud SQL Instance:** project-d84d7c5a-c91d-497b-b78:us-central1:researcher-mysql
- **Cloud SQL DB Name:** researcher_db
- **Cloud SQL User:** researcher_user

---

## Overview

This README explains how to build the Docker image for the researcher backend, store it in Google Artifact Registry, create a Cloud Run Job to run the pipeline, and view job logs. Replace placeholders (e.g. `<DB_NAME>`, `<SECRET_NAME>`) with your project values.

## Prerequisites

- Install and authenticate the Google Cloud SDK (`gcloud`) and Docker.
- Set the active project:

```bash
gcloud config set project project-d84d7c5a-c91d-497b-b78
```

## Prerequisites

- Install and authenticate the Google Cloud SDK (`gcloud`) and Docker.
- Set the active project:

```bash
gcloud config set project project-d84d7c5a-c91d-497b-b78
```

- Enable required APIs if not already enabled:

```bash
gcloud services enable cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

- Make sure you have a Google Artifact Registry repo created (or use the one from these instructions).

## Working directory (Step 0)

Change to the repository root before running build commands:

```bash
cd /Users/tuhina/Desktop/Practicum
```

## Step 1: Build Docker Image

Build and push the container image to Artifact Registry using Cloud Build (tagging the image path used by the Cloud Run job):

```bash
gcloud builds submit . \
  --tag us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ingestion
```

What it does:

- Packages the codebase into a Docker container and uploads the image to Google Artifact Registry at the path the job expects.

## Step 2: Update the Existing Cloud Run Job

Update the job to use the newly pushed image and set runtime options (timeout, memory). Note: DB connection, secrets, and Cloud SQL attachment are expected to be already configured on the existing job.

```bash
gcloud run jobs update researcher-ingestion \
  --image us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ingestion \
  --region us-central1 \
  --task-timeout=24h \
  --memory=8Gi
```

What this does:

- Reconfigures the existing Cloud Run job to use the latest Docker image and runtime settings.

Note:

- Database connection, secrets, and Cloud SQL attachment are already configured in the existing job, so you do not need to re-specify them here unless you must change them.

## Step 3: Verify the Job Configuration

```bash
gcloud run jobs describe researcher-ingestion --region us-central1
```

What this does:

- Shows the current Cloud Run job configuration so you can confirm the image and settings are correct.

## Step 4: Execute the Job

Run the job. The example below passes the pipeline arguments as a single `--args` value (comma-separated list) which will be forwarded to the container process.

```bash
gcloud run jobs execute researcher-ingestion \
  --region us-central1 \
  --args="--query=robotics,--start-date=2025-01-01,--end-date=2025-01-31,--region=US,--force"
```

What this does:

- Starts one execution of the ingestion pipeline running with the provided CLI arguments.

## Step 5: View Executions and Logs

List recent job executions and check statuses:

```bash
gcloud run jobs executions list --job researcher-ingestion --region us-central1
```

To view logs for a specific execution, open the Cloud Console Logs viewer or inspect logs with `gcloud logging` filtered by the execution ID. Cloud Run Jobs executions also surface logs under Cloud Run → Jobs → researcher-ingestion → Executions in the Cloud Console.

## Additional Tips and Troubleshooting

- Ensure the service account used by Cloud Run has these IAM roles at minimum:
  - `roles/cloudsql.client` (Cloud SQL Client)
  - `roles/secretmanager.secretAccessor` (Secret Manager access)
  - `roles/run.invoker` / `roles/run.admin` as needed for management
- If the job cannot connect to the DB:
  - Confirm the Cloud SQL instance and instance connection name match (`project:region:instance`).
  - Confirm the job has `--set-cloudsql-instances` configured (attached) or equivalent configuration.
  - Confirm the DB secret name exists in Secret Manager and the service account can access it.
- For automation / CI, consider creating a short GitHub Actions workflow that runs `gcloud builds submit` and `gcloud run jobs update` on pushes to main.

## Where to find files in this repo

- The main pipeline controller is in `researcher-kb-pipeline/pipeline.py` and Stage files live in `researcher-kb-pipeline/stage1_discover.py`, `stage2_extract.py`, `stage3_enrich.py`, and `stage4_assemble.py`.

---

If you want, I can add a small GitHub Actions CI example that builds and updates the Cloud Run job automatically, or add explicit commands to create the Artifact Registry repository and Secret Manager secrets.

- Add exact IAM/Service Account setup commands.

## Ranking Service (Cloud Run) — Updated Flow

This project now includes a small FastAPI ranking service that serves `/rank` (JSON). Keep ingestion unchanged; follow one of the two flows below depending on whether you're updating the ingestion _job_ or the ranking _service_.

**Build & push (ranking image)**

Run from the repository root:

```bash
gcloud builds submit . \
  --config cloudbuild.rank.yaml \
  --project project-d84d7c5a-c91d-497b-b78
```

This creates and pushes the image to Artifact Registry (example path used by the repo):

`us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ranking:latest`

**Deploy or update the Cloud Run _service_ (ranking)**

Make sure the runtime service account has these roles: `roles/cloudsql.client`, `roles/secretmanager.secretAccessor`, `roles/aiplatform.user` (if using Vertex embeddings). Then deploy (or update) with Cloud SQL attached and secrets bound:

```bash
gcloud run deploy researcher-ranking \
  --image us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ranking:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account=researcher-run-sa@project-d84d7c5a-c91d-497b-b78.iam.gserviceaccount.com \
  --add-cloudsql-instances=project-d84d7c5a-c91d-497b-b78:us-central1:researcher-mysql \
  --set-secrets DB_PASSWORD=db-password:latest,PINECONE_API_KEY=pinecone-key:latest \
  --set-env-vars DB_HOST=/cloudsql/project-d84d7c5a-c91d-497b-b78:us-central1:researcher-mysql,DB_USER=researcher_user,DB_NAME=researcher_db,DB_PORT=3306,GOOGLE_CLOUD_PROJECT=project-d84d7c5a-c91d-497b-b78,VERTEX_LOCATION=us-central1
```

Notes:

- Use `--set-secrets` to bind Secret Manager secrets (keeps values out of command history).
- `DB_HOST` when using Cloud SQL should be the socket path `/cloudsql/<INSTANCE_CONNECTION_NAME>`.

**Persist secret bindings on the service**

If you prefer to bind secrets separately (or after initial deploy), use:

```bash
gcloud run services update researcher-ranking \
  --region us-central1 \
  --set-secrets DB_PASSWORD=db-password:latest,PINECONE_API_KEY=pinecone-key:latest \
  --update-env-vars DB_HOST=/cloudsql/project-d84d7c5a-c91d-497b-b78:us-central1:researcher-mysql,DB_USER=researcher_user,DB_NAME=researcher_db,DB_PORT=3306
```

This updates the live service revision without rebuilding the image.

**How to update the Cloud Run _job_ (ingestion) after an image change**

If you change the ingestion image or code (job), rebuild the image and update the job:

```bash
gcloud builds submit . --tag us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ingestion

gcloud run jobs update researcher-ingestion \
  --image us-central1-docker.pkg.dev/project-d84d7c5a-c91d-497b-b78/researcher-repo/researcher-ingestion \
  --region us-central1 \
  --task-timeout=24h --memory=8Gi
```

Then execute the job (example):

```bash
gcloud run jobs execute researcher-ingestion \
  --region us-central1 \
  --args="--query=robotics,--start-date=2025-01-01,--end-date=2025-01-31,--region=US,--force"
```

The job keeps its previous secret and Cloud SQL configuration unless you explicitly change them with `gcloud run jobs update`.

**Minimal curl examples (ranking service)**

- Default cap (service default, e.g. 25):

```bash
curl -s -X POST https://researcher-ranking-843231871344.us-central1.run.app/rank \
  -H "Content-Type: application/json" \
  -d '{"query":"robotics","use_mock_data":false}'
```

- Explicit `limit` (return up to 100 results):

```bash
curl -s -X POST https://researcher-ranking-843231871344.us-central1.run.app/rank \
  -H "Content-Type: application/json" \
  -d '{"query":"robotics","use_mock_data":false,"limit":100}'
```

Expected output (truncated example — HTTP 200):

```json
{
  "results": [
    {
      "researcher_id": "A5110885212",
      "name": "R. Kelly Rainer",
      "institution": "Auburn University",
      "final_score": 0.75188,
      "reason": {
        "primary_driver": "relevance",
        "top_papers": [
          {
            "paper_id": "10.1111/jbl.70005",
            "year": 2025,
            "similarity": 0.6431
          }
        ]
      }
    }
  ],
  "returned": 25
}
```

If you receive an error like `Missing required database environment variables: DB_HOST, DB_USER, DB_NAME` it means the service revision is missing the DB envs or Cloud SQL attachment — run the `gcloud run services update` example above and redeploy.

**Quick IAM checklist**

- Grant the runtime service account (`researcher-run-sa@...`) at minimum:
  - `roles/cloudsql.client`
  - `roles/secretmanager.secretAccessor`
  - `roles/aiplatform.user` (if using Vertex)
- Grant deployer the `roles/iam.serviceAccountUser` on the runtime SA to allow `gcloud run deploy --service-account=...`.

---

If you'd like, I can add a tiny CI script (GitHub Actions) that builds the ranking image and updates the Cloud Run service automatically on push.
