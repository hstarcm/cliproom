"""Identifier generation (FR-1, SR-1): room IDs are base62, >=22 chars."""

from __future__ import annotations

import secrets
import uuid

BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ROOM_ID_LENGTH = 22  # >= 22 chars * log2(62) ≈ 131 bits of entropy


def new_room_id(length: int = ROOM_ID_LENGTH) -> str:
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))


def new_uuid() -> str:
    """Internal surrogate UUID (room_uuid, member_id, item_id, file_id)."""
    return uuid.uuid4().hex


def is_base62(value: str) -> bool:
    return all(c in BASE62_ALPHABET for c in value)
