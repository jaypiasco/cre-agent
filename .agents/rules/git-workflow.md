---
trigger: always_on
---

# Git & PR Workflow

- Never push directly to `main`.
- Use the two-stage PR flow (`feature` -> `dev` -> `main`):
  1. Create a descriptive feature branch (e.g., `feat/...`, `fix/...`, `chore/...`).
  2. Run the project's lint, test, and build checks before committing.
  3. Commit with a clear conventional commit message, push the branch to `origin`, and open a Pull Request into `dev` via `gh pr create --base dev`.
  4. Promote `dev` to `main` via `gh pr create --base main --head dev` (follow `.agents/skills/ship-pr/SKILL.md`).
