# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in CRE-Agent, please **do not** open a public GitHub issue. Instead, report it privately to the repository maintainers via GitHub Security Advisories or direct email.

## Security Practices

- **No Secrets in Source Control:** API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LANGFUSE_SECRET_KEY`) must only be supplied via environment variables or `.env` (git-ignored).
- **Strict Input Validation:** All uploaded files are validated for `.pdf` extension and parsed safely via PyMuPDF with page count limits (`PDF_MAX_VISION_PAGES`).
- **Deterministic Financial Gates:** Arithmetic totals and required fields are verified deterministically in Python (`Decimal`) before any invoice can be marked `VALID`.
- **Human-in-the-Loop Enforcement:** Export endpoints (`/api/v1/invoices/export`) reject payloads unless `human_approved` is explicitly `true`.
