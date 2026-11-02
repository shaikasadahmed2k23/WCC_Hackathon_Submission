#!/usr/bin/env bash
# One-time setup + run for macOS/Linux. Run from the project root.
set -e
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements.txt
(cd frontend && ([ -d node_modules ] || npm install --no-audit --no-fund) && npm run build)
echo "Open http://localhost:8000"
cd backend && ../backend/.venv/bin/python -m uvicorn app.main:app --port 8000
