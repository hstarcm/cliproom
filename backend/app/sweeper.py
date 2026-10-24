"""Background sweeper (FR-20): hourly (SWEEPER_INTERVAL_MIN) deletion of
expired rooms + their files + orphaned uploads, recorded in sweeper_runs.

Pure sync function — callable from APScheduler, tests, and the on-call agent.
"""

from __future__ import annotations

import logging
import os
import time as _time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import session_factory
from .models import Item, Room, SweeperRun, iso_utc, utcnow
from .rooms import delete_room_files

logger = logging.getLogger("cliproom.sweeper")


def run_sweep(settings: Settings, db: Session | None = None) -> dict:
    """One sweeper run. Returns the recorded row as a dict."""
    own_session = db is None
    db = db or session_factory()()
    run = SweeperRun(started_at=utcnow(), status="running")
    db.add(run)
    db.commit()

    rooms_deleted = 0
    files_deleted = 0
    orphans_deleted = 0
    status = "ok"
    try:
        # 1. expired rooms → delete rows (cascade) + disk directories
        expired = db.query(Room).filter(Room.expires_at <= utcnow()).all()
        for room in expired:
            files_deleted += delete_room_files(settings, room.room_id)
            db.delete(room)
            rooms_deleted += 1
        db.commit()

        # 2. orphaned files on disk with no DB row (e.g. crash mid-upload)
        known_paths = set(
            db.execute(select(Item.file_path)).scalars()
        )
        if os.path.isdir(settings.data_dir):
            for room_dir_name in os.listdir(settings.data_dir):
                room_dir = os.path.join(settings.data_dir, room_dir_name)
                if not os.path.isdir(room_dir):
                    continue
                for file_name in os.listdir(room_dir):
                    path = os.path.join(room_dir, file_name)
                    if path not in known_paths:
                        try:
                            os.remove(path)
                            orphans_deleted += 1
                        except OSError:
                            pass
                # remove empty room dirs whose room row is gone
                if not os.listdir(room_dir):
                    room_row_exists = db.get(Room, room_dir_name) is not None
                    if not room_row_exists:
                        try:
                            os.rmdir(room_dir)
                        except OSError:
                            pass
        run.finished_at = utcnow()
    except Exception as exc:  # noqa: BLE001 — record and re-raise for scheduler
        run.status = "error"
        status = "error"
        run.finished_at = utcnow()
        logger.error("sweeper run failed: %s", exc)
        raise
    finally:
        run.rooms_deleted = rooms_deleted
        run.files_deleted = files_deleted
        run.orphans_deleted = orphans_deleted
        run.status = status
        db.commit()
        if status == "ok":
            from .telemetry import sweeper_last_success

            sweeper_last_success.set(_time.time())
        if own_session:
            db.close()
    return {
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
        "rooms_deleted": rooms_deleted,
        "files_deleted": files_deleted,
        "orphans_deleted": orphans_deleted,
        "status": status,
    }


def start_scheduler(settings: Settings):
    """APScheduler in-process job (FR-20). Returns the scheduler (started)."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_sweep,
        "interval",
        minutes=settings.sweeper_interval_min,
        args=[settings],
        id="sweeper",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
