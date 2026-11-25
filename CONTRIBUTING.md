# Contributing to CRE-Agent

Thank you for your interest in contributing to CRE-Agent!

## Development Setup

1. **Backend (Python 3.13+)**
   ```bash
   python -m venv .venv
   # Windows: .\.venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
   Set `LLM_PROVIDER=mock` in `.env` for offline development, or provide `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.

2. **Frontend (Node 22+)**
   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

## Quality Checks

Before opening a pull request, ensure all checks pass:

```bash
ruff check app scripts tests
pytest -v
python scripts/eval_pipeline.py --provider mock
cd frontend && npm run lint && npm run build
```

## Pull Request Guidelines

- Keep changes focused and well-tested.
- Never commit `.env` files, API keys, or generated export artifacts.
- Follow existing code style (`ruff` for Python, `eslint` + TypeScript strict mode for Next.js).
