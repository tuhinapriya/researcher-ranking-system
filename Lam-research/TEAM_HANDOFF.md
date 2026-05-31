# ResearchAI Team Preview Notes

## Email Draft

Subject: ResearchAI test build update and local run instructions

Hi team,

I am sharing a test build of ResearchAI for review. This version now uses the shared ranking backend as the primary data source, so the frontend no longer depends on its own OpenAlex search path.

Main updates:

- Added explicit search modes: Auto, Name, Query, and Institution.
- All search modes now call the ranking backend through the app's Express API.
- The frontend passes `search_type`, `author_query`, `institution_query`, or `topic_query` when applicable, so backend-side strong filters can be enforced there.
- The results table now shows Q and R. H-index is profile context only.
- Q now means normalized query relevance. R means citations received by matched papers during the selected citation year range.
- The citation year range is debounced, so dragging the range does not continuously trigger ranking backend requests.
- UI readability and layout were improved, including light mode contrast and screen-size scaling in Settings.

Please treat this as a local preview build rather than a production release. Backend ranking and filter behavior should still be validated against expert expectations before production use.

How to run it locally is included below. After running it, try a few searches such as:

- Name: `Khaled B. Letaief`
- Institution: `Hebrew University of Jerusalem`
- Query: `post-quantum cryptography`

Best,

[Your Name]

## What Changed Today

### 1. Search mode selector

The search bar now lets users choose:

- `Auto`: default ranking backend search.
- `Name`: sends `search_type=author` and `author_query`.
- `Query`: sends `search_type=topic` and `topic_query`.
- `Institution`: sends `search_type=institution` and `institution_query`.

This avoids one input box silently mixing person, topic, and institution searches.

### 2. Backend search routing

The frontend now routes every search mode through the shared ranking backend endpoint rather than querying its own researcher data source.

The backend is responsible for researcher lookup, matched papers, Q/R ranking signals, and any strong author or institution filters.

### 3. Matched institution vs current institution

Institution search now keeps two separate concepts:

- `Matched institution`: the institution that caused the result to match the search.
- `Current institution`: the author's current or last-known institution if returned by the backend profile.

This matters because researchers can move institutions. The UI keeps these fields separate when the backend returns both values.

### 4. Ranking and explainability

The app now exposes:

- Q_norm: normalized query relevance
- R_raw: citations received during the selected citation year range
- R_norm: log-normalized recent citation impact
- Final score: `wQ * Q_norm + wR * R_norm`
- H-index as profile-only context
- Lifetime citations as profile-only context
- Result match source, such as exact name, author search, topic relevance, or institution search

The goal is to make it easier to understand why someone appears in a result list.

## External Ranking Backend Proxy

The Express server can proxy requests to the separate FastAPI ranking backend:

```text
GET  /api/ranking/health
POST /api/ranking/rank
```

Configure the upstream service with:

```text
RANKING_API_URL=https://researcher-ranking-843231871344.us-central1.run.app
RANKING_API_AUTH_TOKEN=
```

The browser should call the Express routes above. It should not call the Cloud Run URL directly. Backend-only secrets for the FastAPI service, such as MySQL credentials or Pinecone keys, should stay in that service's own cloud environment and should not be copied into this app.

The proxy explicitly sends Q/R weights to the ranking backend. If the browser request omits weights, the proxy uses the product default:

```text
q_weight = 0.7
r_weight = 0.3
```

It also accepts slider-style aliases such as `wQ`/`wR` or percentage-style values such as `70`/`30`, then normalizes them before forwarding the request.

### 5. Citation year range

The year selector now means citation year range, not publication year range.

Example: `2020-2026` counts citations received between 2020 and 2026, including citations to older papers. A paper published in 2000 can still contribute to R if it was cited during the selected citation window.

The default ranking favors query relevance:

```text
wQ = 0.7
wR = 0.3
Final Score = wQ * Q_norm + wR * R_norm
```

The sliders also allow query-only ranking (`wQ = 1, wR = 0`) and citation-impact-only ranking (`wQ = 0, wR = 1`).

H-index is deliberately not part of the default ranking score. It remains visible in the table and profile detail page so reviewers can inspect researcher seniority or bibliometric context without mixing it into the Q/R score.

## Local Run Instructions

### Requirements

Install these first:

- Node.js 20 or newer. Node.js 22 or 24 is also fine.
- pnpm 10.x.

If pnpm is not installed:

```bash
npm install -g pnpm
```

### Step 1: Unzip the project

Unzip the shared file, then open a terminal in the project folder:

```bash
cd research-ai
```

On Windows PowerShell, the path may look like:

```powershell
cd C:\Users\YOUR_NAME\Downloads\research-ai
```

### Step 2: Create the environment file

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and confirm the ranking backend URL:

```env
RANKING_API_URL=https://researcher-ranking-843231871344.us-central1.run.app
PORT=3000
```

The search UI uses the shared ranking backend as its data source. AI chat keys are entered by each user inside the app Settings screen, so do not put personal OpenAI/Gemini/Claude keys in `.env` unless intentionally configuring a shared server fallback.

### Step 3: Install dependencies

```bash
pnpm install
```

If PowerShell blocks `pnpm.ps1`, use:

```powershell
pnpm.cmd install
```

### Step 4: Run the development server

```bash
pnpm run dev
```

Then open the URL shown in the terminal. It is usually:

```text
http://localhost:5173
```

If PowerShell blocks the command:

```powershell
pnpm.cmd run dev
```

### Step 5: Run a production-style local build

To test the bundled server:

```bash
pnpm run build
pnpm run start
```

Then open:

```text
http://localhost:3000
```

If `PORT` is changed in `.env`, use that port instead.

## Suggested Package Contents

When creating a zip for teammates, include:

- `client/`
- `server/`
- `shared/`
- `scripts/`
- `patches/`
- `.env.example`
- `package.json`
- `pnpm-lock.yaml`
- `tsconfig.json`
- `tsconfig.node.json`
- `vite.config.ts`
- `components.json`
- `render.yaml`
- `Dockerfile`
- `DEPLOYMENT.md`
- `TEAM_HANDOFF.md`

Do not include:

- `node_modules/`
- `.pnpm-store/`
- `dist/`
- `.manus-logs/`
- local `.env`

Those folders are either very large, generated, or local/private.

## Windows Zip Command

From PowerShell, this creates a clean zip on the Desktop:

```powershell
$src = "C:\Users\kongb\Desktop\research-ai"
$zip = "C:\Users\kongb\Desktop\research-ai-team-preview.zip"
$temp = Join-Path $env:TEMP "research-ai-team-preview"

Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $temp | Out-Null

$exclude = @("node_modules", ".pnpm-store", "dist", ".manus-logs", "backups", ".env")
Get-ChildItem -LiteralPath $src -Force |
  Where-Object { $exclude -notcontains $_.Name } |
  Copy-Item -Destination $temp -Recurse -Force

Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $zip -Force
Write-Host "Created $zip"
```

## Current Limitations

- Backend ranking and strong-filter behavior should still be validated with representative queries.
- Institution matches may reflect historical paper affiliations if the backend includes them.
- Q is normalized query relevance from the ranking backend.
- R is citation-window impact from the ranking backend and depends on the selected citation year range.
- AI chat requires each tester to provide their own API key in Settings.
- This is still a preview build and not yet a hosted production deployment.
