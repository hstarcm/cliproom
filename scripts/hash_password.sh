#!/usr/bin/env bash
# Generate an argon2id password hash for ADMIN_PASSWORD_HASH / GUEST_PASSWORD_HASH.
# Usage: bash scripts/hash_password.sh 'my-secret'
set -euo pipefail
cd "$(dirname "$0")/.."

PY=backend/.venv/Scripts/python
[ -x "$PY" ] || PY=backend/.venv/bin/python

"$PY" - "$1" <<'EOF'
import sys
from argon2 import PasswordHasher

if len(sys.argv) != 2:
    raise SystemExit("usage: hash_password.sh <password>")
print(PasswordHasher().hash(sys.argv[1]))
EOF
