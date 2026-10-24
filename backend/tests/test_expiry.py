"""FR-19/FR-20: expiry math, TTL extension, sweeper behavior, orphans."""

from __future__ import annotations

from datetime import timedelta

from app.config import get_settings
from app.db import init_engine, session_factory
from app.ids import new_room_id
from app.models import Room, utcnow
from app.rooms import create_room, get_active_room, room_dir, touch_room
from app.sweeper import run_sweep


def _db(env):
    init_engine(str(env / "expiry.db"))
    from app.models import Base

    Base.metadata.create_all(init_engine(str(env / "expiry.db"))[0])
    return session_factory()()


def test_ttl_extension_on_activity(env):
    db = _db(env)
    room = create_room(db, "admin", "1h")
    before = room.expires_at
    # simulate 10 minutes passing, then activity
    room.last_activity_at = utcnow()
    touch_room(db, room)
    assert room.expires_at > before
    assert room.expires_at - room.last_activity_at == timedelta(seconds=3600)


def test_sweeper_deletes_expired_keeps_active(env):
    db = _db(env)
    expired = create_room(db, "admin", "1h")
    active = create_room(db, "admin", "24h")
    expired.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    summary = run_sweep(get_settings(), db)
    assert summary["status"] == "ok"
    assert summary["rooms_deleted"] == 1
    assert db.get(Room, expired.room_id) is None
    assert db.get(Room, active.room_id) is not None
    assert get_active_room(db, expired.room_id) is None
    assert get_active_room(db, active.room_id) is not None


def test_sweeper_cleans_room_files_and_orphans(env):
    settings = get_settings()
    db = _db(env)
    room = create_room(db, "admin", "1h")
    room.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    import os

    # legit file belonging to the (now expired) room
    os.makedirs(room_dir(settings, room.room_id), exist_ok=True)
    room_file = os.path.join(room_dir(settings, room.room_id), "aaa")
    open(room_file, "wb").close()

    # orphan: room dir with no DB row at all
    orphan_dir = os.path.join(settings.data_dir, new_room_id())
    os.makedirs(orphan_dir, exist_ok=True)
    orphan_file = os.path.join(orphan_dir, "orphan.bin")
    open(orphan_file, "wb").close()

    summary = run_sweep(settings, db)
    assert summary["rooms_deleted"] == 1
    assert summary["orphans_deleted"] == 1
    assert not os.path.exists(room_file)
    assert not os.path.exists(orphan_file)


def test_sweeper_records_run_in_table(env):
    db = _db(env)
    from app.models import SweeperRun

    run_sweep(get_settings(), db)
    rows = db.query(SweeperRun).all()
    assert len(rows) >= 1
    assert rows[-1].status == "ok"
    assert rows[-1].finished_at is not None


def test_expired_room_404_via_api(client, env):
    from tests.conftest import operator_login

    operator_login(client, "admin", "cliproom-dev-admin")
    r = client.post(
        "/api/rooms",
        json={"ttl": "1h"},
        headers={"X-Requested-With": "fetch"},
    )
    room_id = r.json()["room_id"]

    # force-expire directly in the app's DB (already initialised by lifespan)
    from app.db import session_factory

    db = session_factory()()
    try:
        room = db.get(Room, room_id)
        room.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    assert client.get(f"/api/rooms/{room_id}").status_code == 404
    assert client.get(f"/api/rooms/{room_id}/items").status_code == 404
