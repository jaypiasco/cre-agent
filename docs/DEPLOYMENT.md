# Deployment Guide (AWS App Runner + Vercel + Langfuse)

This guide covers deploying **CRE-Agent** for production/portfolio use with zero cold starts:
- **Backend (`app/`):** Containerized FastAPI on **AWS App Runner** (via Amazon ECR or GitHub source connection).
- **Frontend (`frontend/`):** Next.js App Router on **Vercel**.
- **Observability:** **Langfuse** (Cloud Hobby tier).

---

## 1. Prerequisites

- AWS account (with App Runner & ECR permissions)
- Vercel account
- Google AI Studio API key (`GEMINI_API_KEY`) — free tier supported, or OpenAI / Anthropic key
- Optional: Langfuse Cloud project (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`)

---

## 2. Deploy FastAPI Backend to AWS App Runner

### Option A: Via Amazon ECR (Recommended)

1. **Create an ECR repository** (e.g., `cre-agent-api` in `us-east-1`).
2. **Build and push the Docker image:**
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
   docker build -t cre-agent-api .
   docker tag cre-agent-api:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/cre-agent-api:latest
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/cre-agent-api:latest
   ```
3. **Create an App Runner service:**
   - Source: **Container registry -> Amazon ECR** -> select `cre-agent-api:latest`.
   - Port: `8000`
   - Health check path: `/health`
   - Environment variables:
     - `LLM_PROVIDER=gemini` (or `mock` for key-free demo)
     - `GEMINI_API_KEY=<your-key>`
     - `LANGFUSE_PUBLIC_KEY=<optional>`
     - `LANGFUSE_SECRET_KEY=<optional>`
     - `LANGFUSE_HOST=https://cloud.langfuse.com`
4. Copy the generated App Runner service URL (e.g., `https://xxxxxxxxxx.us-east-1.awsapprunner.com`).

---

## 3. Deploy Next.js Frontend to Vercel

1. Import the GitHub repository in **Vercel**.
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `NEXT_PUBLIC_API_URL=https://xxxxxxxxxx.us-east-1.awsapprunner.com`
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
