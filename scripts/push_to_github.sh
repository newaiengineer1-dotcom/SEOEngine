#!/usr/bin/env bash
# Upload this project to a NEW private GitHub repo (needs git + GitHub CLI: https://cli.github.com, then `gh auth login`).
set -euo pipefail
NAME="${1:-kunergy-seo-autopilot}"
[ -d .git ] || git init -b main
git add .
git commit -m "Kunergy SEO Autopilot: initial commit" || true
gh repo create "$NAME" --private --source=. --remote=origin --push
echo "Done. Next: https://share.streamlit.io -> New app -> pick $NAME, main file app.py, then add secrets (see .streamlit/secrets.toml.example)."
