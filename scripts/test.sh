#!/usr/bin/env bash
# Single command for every test suite (AC14 / SPECS.md §9).
#   backend:  pytest (unit + integration)
#   frontend: vitest
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== backend: pytest ==="
if [ ! -d backend/.venv ]; then
  python -m venv backend/.venv
  backend/.venv/Scripts/pip install -q -e "backend[dev]" 2>/dev/null \
    || backend/.venv/bin/pip install -q -e "backend[dev]"
fi
( cd backend && ./.venv/Scripts/python -m pytest ) 2>/dev/null \
  || ( cd backend && ./.venv/bin/python -m pytest )

echo "=== frontend: vitest ==="
cd frontend
[ -d node_modules ] || npm ci
npx vitest run

echo "=== all suites passed ==="
