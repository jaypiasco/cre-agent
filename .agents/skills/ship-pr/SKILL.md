---
name: ship-pr
description: Automate the two-stage Git & GitHub PR workflow for CRE-Agent: run lint/test/build checks, ship feature branches into dev via PR, and promote dev into main via PR using gh CLI. Use whenever the user asks to ship, open a PR, merge to dev, or release to main.
---

# Ship PR Workflow (`feature` -> `dev` -> `main`)

Follow this two-stage PR workflow using `gh` CLI. Never push directly to `main`.

## Pre-Flight Checks

1. Verify `gh` is authenticated:
   ```powershell
   gh auth status
   ```
   If not authenticated, stop and ask the user to run `gh auth login`.
2. Check current branch and working tree:
   ```powershell
   git branch --show-current; git status -sb
   ```
   - If currently on `main`, create/switch to a descriptive feature branch (`feat/...`, `fix/...`, `chore/...`) before committing.

## Stage 1: Feature Branch -> `dev`

1. **Run all quality checks** before committing:
   ```powershell
   .venv\Scripts\python.exe -m ruff check app tests scripts
   .venv\Scripts\python.exe -m pytest -q
   cd frontend; npm run lint; npm run build
   ```
2. **Commit & push** the feature branch (never commit `.env` or secrets):
   ```powershell
   git add <files>
   git commit -m "<type>: <concise summary>"
   git push -u origin <feature-branch>
   ```
3. **Open (or update) PR into `dev`**:
   ```powershell
   gh pr create --base dev --head <feature-branch> --fill
   ```
   - If the user asked to merge into `dev` immediately and checks pass:
     ```powershell
     gh pr merge --squash --delete-branch
     ```

## Stage 2: Promote `dev` -> `main`

1. Ensure `origin/dev` is up to date:
   ```powershell
   git fetch origin dev main
   ```
2. Check if an open `dev` -> `main` PR already exists; if not, create one:
   ```powershell
   gh pr list --base main --head dev --state open
   gh pr create --base main --head dev --title "release: merge dev into main" --fill
   ```
3. Report both PR URLs to the user.
