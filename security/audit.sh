#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORTS="$ROOT/security/reports"
mkdir -p "$REPORTS"

if ! command -v pip-audit >/dev/null 2>&1; then
  echo "pip-audit no está instalado. Ejecute: python -m pip install pip-audit" >&2
  exit 2
fi

echo "[1/3] Backend Python audit"
pip-audit -r "$ROOT/backend/requirements.txt" 2>&1 | tee "$REPORTS/backend-pip-audit.txt"; B=${PIPESTATUS[0]}
echo "[2/3] Ingestion Python audit"
pip-audit -r "$ROOT/ingestion/requirements.txt" 2>&1 | tee "$REPORTS/ingestion-pip-audit.txt"; I=${PIPESTATUS[0]}
echo "[3/3] Frontend npm audit"
if [ ! -f "$ROOT/frontend/package-lock.json" ]; then
  echo "package-lock.json missing; generating lockfile for reproducible npm audit..."
  (cd "$ROOT/frontend" && npm install --package-lock-only --ignore-scripts) || exit 3
fi
(cd "$ROOT/frontend" && npm audit --json) > "$REPORTS/frontend-npm-audit.json" 2>&1; N=$?

echo "Reports saved under security/reports (exit codes backend=$B ingestion=$I npm=$N)"
exit $(( B || I || N ))
