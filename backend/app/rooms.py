"""Room lifecycle service (FR-1, FR-2, FR-19, FR-13a) — shared by routers,
sweeper and the on-call agent."""

from __future__ import annotations

import os
import re
import shutil
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import Settings
from .ids import new_room_id, new_uuid
from .models import Item, Room, utcnow

TTL_CHOICES = {"1h": 3600, "24h": 86400, "7d": 604800}
_CUSTOM_TTL = re.compile(r"^(\d{1,4})([mhd])$")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 365 * 86400


def parse_ttl(value: str) -> int | None:
    """FR-19: 'forever' → None (no expiry); presets; or '<n>m|h|d' within
    1 minute – 365 days. Raises ValueError for anything else."""
    v = (value or "").strip().lower()
    if v == "forever":
        return None
    if v in TTL_CHOICES:
        return TTL_CHOICES[v]
    m = _CUSTOM_TTL.match(v)
    if not m:
        raise ValueError("ttl must be 1h/24h/7d, '<n>m|h|d' (1m–365d), or 'forever'")
    seconds = int(m.group(1)) * _UNIT_SECONDS[m.group(2)]
    if not (MIN_TTL_SECONDS <= seconds <= MAX_TTL_SECONDS):
        raise ValueError("custom ttl must be between 1 minute and 365 days")
    return seconds


def effective_max_file_mb(settings: Settings, room: Room) -> int:
    """FR-13a: the room's own cap when set, else the global cap."""
    return room.max_file_mb if room.max_file_mb else settings.max_file_mb


def create_room(db: Session, created_by: str, ttl_label: str, max_file_mb: int | None = None) -> Room:
    ttl_seconds = parse_ttl(ttl_label)  # None → forever
    now = utcnow()
    room = Room(
        room_id=new_room_id(),
        room_uuid=new_uuid(),
        created_by=created_by,
        created_at=now,
        ttl_seconds=ttl_seconds,
        expires_at=None if ttl_seconds is None else now + timedelta(seconds=ttl_seconds),
        max_file_mb=max_file_mb,
        last_activity_at=now,
    )
    db.add(room)
    db.commit()
    return room


def get_active_room(db: Session, room_id: str) -> Room | None:
    room = db.get(Room, room_id)
    if room is None:
        return None
    if room.expires_at is None:  # forever
        return room
    if room.expires_at <= utcnow():
        return None
    return room


def guest_active_room(db: Session) -> Room | None:
    """The guest account's single active room, if any (FR-7). Forever rooms
    count as active."""
    return (
        db.query(Room)
        .filter(
            Room.created_by == "guest",
            or_(Room.expires_at.is_(None), Room.expires_at > utcnow()),
        )
        .order_by(Room.created_at.desc())
        .first()
    )


def touch_room(db: Session, room: Room) -> None:
    """FR-19: activity extends expires_at = now + ttl; viewing does not.
    Forever rooms have no expiry to extend."""
    room.last_activity_at = utcnow()
    if room.ttl_seconds is not None:
        room.expires_at = room.last_activity_at + timedelta(seconds=room.ttl_seconds)
    db.commit()


def room_disk_usage(db: Session, room_id: str) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(Item.file_size), 0)).where(
            Item.room_id == room_id, Item.kind == "file"
        )
    ).scalar_one()
    return int(total)


def room_dir(settings: Settings, room_id: str) -> str:
    return os.path.join(settings.data_dir, room_id)


def delete_room_files(settings: Settings, room_id: str) -> int:
    """Remove the room's upload directory; returns files removed (0 or dir)."""
    path = room_dir(settings, room_id)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        return 1
    return 0


def terminate_room(db: Session, settings: Settings, room: Room) -> None:
    """Delete the room row (cascades items/members) and its files on disk."""
    delete_room_files(settings, room.room_id)
    db.delete(room)
    db.commit()
