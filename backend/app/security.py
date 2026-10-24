"""Security primitives: password verification (FR-3/FR-4), member token
hashing (FR-9, SR-2), constant-time comparisons, operator sessions (SR-7)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from bcrypt import checkpw

_ph = PasswordHasher()  # argon2id defaults


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification of argon2id or bcrypt hashes.

    Both libraries re-derive the hash from the input and compare fixed-length
    digests; no early-exit string comparison is used.
    """
    if password_hash.startswith("$argon2"):
        try:
            return _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False
    if password_hash.startswith("$2"):
        try:
            return checkpw(password.encode(), password_hash.encode())
        except ValueError:
            return False
    return False


def hash_member_token(token: str) -> str:
    """SHA-256 hex of a member token — the only thing ever stored (SR-2)."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    """Constant-time member-token comparison against a stored hash."""
    return hmac.compare_digest(hash_member_token(token), token_hash)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def agent_tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_agent_token(token), token_hash)


# --- operator sessions (FR-4, SR-7) ---------------------------------------
# In-memory store: the deployment is a single uvicorn worker; a restart logs
# everyone out, which is acceptable and arguably desirable. Sessions expire
# after 12 h and are invalidated server-side on logout.

SESSION_TTL_SECONDS = 12 * 3600


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def create(self, username: str, role: str, now: float | None = None) -> str:
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = {
            "username": username,
            "role": role,
            "expires_at": (now if now is not None else time.time()) + SESSION_TTL_SECONDS,
        }
        return sid

    def get(self, sid: str, now: float | None = None) -> dict | None:
        session = self._sessions.get(sid)
        if session is None:
            return None
        current = time.time() if now is None else now
        if current >= session["expires_at"]:
            self._sessions.pop(sid, None)
            return None
        return session

    def destroy(self, sid: str) -> None:
        self._sessions.pop(sid, None)


sessions = SessionStore()
