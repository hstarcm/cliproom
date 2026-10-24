"""Room lifecycle service (FR-1, FR-2, FR-19) — shared by routers, sweeper
and the on-call agent."""

from __future__ import annotations

import os
import shutil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .ids import new_room_id, new_uuid
from .models import Item, Room, utcnow

TTL_CHOICES = {"1h": 3600, "24h": 86400, "7d": 604800}


def create_room(db: Session, created_by: str, ttl_label: str) -> Room:
    ttl_seconds = TTL_CHOICES[ttl_label]
    now = utcnow()
    room = Room(
        room_id=new_room_id(),
        room_uuid=new_uuid(),
        created_by=created_by,
        created_at=now,
        ttl_seconds=ttl_seconds,
        expires_at=_ts_plus(now, ttl_seconds),
        last_activity_at=now,
    )
    db.add(room)
    db.commit()
    return room


def get_active_room(db: Session, room_id: str) -> Room | None:
    room = db.get(Room, room_id)
    if room is None or room.expires_at <= utcnow():
        return None
    return room


def guest_active_room(db: Session) -> Room | None:
    """The guest account's single active room, if any (FR-7)."""
    return (
        db.query(Room)
        .filter(Room.created_by == "guest", Room.expires_at > utcnow())
        .order_by(Room.created_at.desc())
        .first()
    )


def touch_room(db: Session, room: Room) -> None:
    """FR-19: activity extends expires_at = now + ttl; viewing does not."""
    room.last_activity_at = utcnow()
    room.expires_at = _ts_plus(room.last_activity_at, room.ttl_seconds)
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


def _ts_plus(base, seconds):
    from datetime import timedelta

    return base + timedelta(seconds=seconds)
