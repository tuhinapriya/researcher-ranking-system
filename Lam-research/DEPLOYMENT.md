# ResearchAI Deployment

ResearchAI is now packaged as a Vite frontend plus a small Express backend. The AI feature uses BYOK: each user supplies their own OpenAI, Gemini, or OpenAI-compatible API key in Settings. The app backend only proxies that key for the current request.

## Local Use

Install dependencies:

```powershell
pnpm install
```

Run the development server:

```powershell
pnpm dev
```

Open:

```text
http://localhost:3000
```

The Vite dev server includes `/api/ai/chat`, so AI chat works in development after the user enters their own API key in Settings.

## Production Build

Build:

```powershell
pnpm build
```

Start:

```powershell
pnpm start
```

Open:

```text
http://localhost:3000
```

Health check:

```text
http://localhost:3000/health
```

## Deploy Test Version To Render

This repo includes `render.yaml`, so Render can create the test web service from a Blueprint.

1. Push this folder to a GitHub repository.
2. Open Render Dashboard.
3. Click **New +**.
4. Choose **Blueprint**.
5. Connect the GitHub repository.
6. Render will read `render.yaml` and create `research-ai-test`.
7. Confirm `RANKING_API_URL` points to the shared ranking backend.
8. Deploy and open the generated `https://...onrender.com` URL.

The Blueprint uses:

```text
Build command: pnpm install --frozen-lockfile && pnpm run build
Start command: node scripts/start.mjs
Health check: /health
Plan: free
```

For a manual Render Web Service instead of Blueprint, use the same commands above.

Environment variables:

```text
NODE_VERSION=22.22.0
NODE_ENV=production
RESEARCH_AI_SHOW_DEV_CODE=false
RANKING_API_URL=https://researcher-ranking-843231871344.us-central1.run.app
RANKING_API_AUTH_TOKEN=optional_only_if_required
```

Render provides `PORT` automatically, so do not hard-code it in the Render service.

The app also includes an Express proxy for the external FastAPI ranking backend:

```text
GET  /api/ranking/health
POST /api/ranking/rank
```

The browser should call these local Express routes instead of calling the Cloud Run ranking service directly. Do not place the ranking service's database password, Pinecone API key, or other backend secrets in this app unless we later decide to redeploy that Python service ourselves.

Free-plan note: the search UI and ranking backend proxy work fine for a demo, but file-backed accounts and saved researchers are not durable on Render's free web service filesystem. Use the test version mainly for search demos; add a managed database before relying on accounts or saved profiles.

## Deploy To Railway

Use these settings:

```text
Build command: pnpm install --frozen-lockfile && pnpm build
Start command: pnpm start
Port: 3000
```

Environment variables:

```text
NODE_ENV=production
PORT=3000
VITE_GOOGLE_CLIENT_ID=
RESEARCH_AI_SHOW_DEV_CODE=false
```

No platform-level OpenAI or Gemini key is required for BYOK.

## Docker

Build:

```powershell
docker build -t research-ai .
```

Run:

```powershell
docker run --rm -p 3000:3000 research-ai
```

## BYOK Security Notes

- Users enter their own API key in Settings.
- The key is sent to `/api/ai/chat` only when the user sends an AI message.
- The backend does not persist the key.
- The frontend only saves the key in browser localStorage if the user enables "Remember key on this device".
- For public deployment, always use HTTPS.

## Accounts And Saved Researchers

The app includes a lightweight local account system so a deployed copy can work without adding Supabase or another auth provider first.

- User accounts, sessions, verification codes, and saved researcher IDs are stored in `data/app-data.json`.
- `data/` is ignored by git because it contains runtime user data.
- Registration uses a generated verification code. In development, the API can return `devCode` so local testing works without email/SMS infrastructure.
- In production, `devCode` is not returned unless `RESEARCH_AI_SHOW_DEV_CODE=true`. For a public service, connect an email/SMS provider before opening registration.
- Google sign-in only opens when `VITE_GOOGLE_CLIENT_ID` is configured. A backend OAuth callback is still required before using Google login in production.

If you deploy with Docker and want accounts to persist after container restarts, mount `/app/data` as a volume.

## Still Needed For A Full SaaS

- Real authentication provider for email, phone, and Google login.
- Database-backed saved researchers and search history.
- Server-side researcher search instead of bundling the full dataset into the frontend.
- Terms/privacy copy explaining BYOK behavior.
- Optional encrypted key storage if users want cross-device key sync.
