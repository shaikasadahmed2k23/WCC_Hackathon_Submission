# One-time setup + run for Windows PowerShell. Run from the project root.
$ErrorActionPreference = "Stop"
if (-not (Test-Path "backend\.venv")) { python -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
Push-Location frontend
if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
npm run build
Pop-Location
Write-Host "Open http://localhost:8000"
Push-Location backend
& .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
