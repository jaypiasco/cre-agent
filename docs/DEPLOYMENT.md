# Deployment Guide (Render + Vercel + Langfuse)

This guide covers deploying **CRE-Agent** for production/portfolio use:
- **Backend (`app/`):** Containerized FastAPI on **Render** (via `render.yaml` / `Dockerfile`).
- **Frontend (`frontend/`):** Next.js App Router on **Vercel**.
- **Observability:** **Langfuse** (Cloud Hobby tier).

---

## 1. Prerequisites

- Render account (connected to GitHub)
- Vercel account (connected to GitHub)
- Optional: Google AI Studio API key (`GEMINI_API_KEY`) or OpenAI / Anthropic key (not required when `LLM_PROVIDER=mock`)
- Optional: Langfuse Cloud project (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`)

---

## 2. Deploy FastAPI Backend to Render

1. Go to [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint** (or **Web Service**).
2. Connect `jaypiasco/cre-agent` (branch `main` or `dev`).
3. Render automatically detects [render.yaml](../render.yaml) and builds from `Dockerfile`:
   - **Runtime:** Docker
   - **Health Check Path:** `/health`
   - **Environment Variables:**
     - `LLM_PROVIDER=mock` *(default for zero-cost live interview demos — pairs with the UI's floating **BYOK** switcher so interviewers can test the 4 built-in sample PDFs immediately or plug in their own key)*
     - Optional: `GEMINI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST=https://cloud.langfuse.com`
4. Copy your generated Render service URL (e.g., `https://cre-agent-api.onrender.com`).

---

## 3. Deploy Next.js Frontend to Vercel

1. Import `jaypiasco/cre-agent` at [vercel.com/new](https://vercel.com/new).
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `NEXT_PUBLIC_API_URL=https://cre-agent-api.onrender.com` *(no trailing slash)*
4. Deploy! Vercel automatically builds with `npm run build` and serves the app globally.

---

## 4. Local Full-Stack Docker Run

Run both services locally with one command:

```bash
cp .env.example .env
# Set LLM_PROVIDER=mock (or gemini with your GEMINI_API_KEY)
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend API & Swagger docs: `http://localhost:8000/docs`
