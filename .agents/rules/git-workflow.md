---
trigger: always_on
---

# Git & PR Workflow

- Never push directly to `main`.
- When asked to ship or push changes:
  1. Create a descriptive feature branch (e.g., `feat/...`, `fix/...`, `chore/...`).
  2. Run the project's lint, test, and build checks before committing.
  3. Commit with a clear conventional commit message, push the branch to `origin`, and open a Pull Request into `main` via `gh pr create`.
