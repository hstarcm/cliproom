"""AC20: custom/forever TTL + per-room upload cap (FR-19, FR-13a)."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest

from tests.conftest import join, operator_login


def _auth_headers():
    return {"X-Requested-With": "fetch"}


def _create(client, body):
    return client.post("/api/rooms", json=body, headers=_auth_headers())


# --- parse_ttl unit ----------------------------------------------------------

def test_parse_ttl_presets_and_custom_and_forever():
    from app.rooms import parse_ttl

    assert parse_ttl("1h") == 3600
    assert parse_ttl("24h") == 86400
    assert parse_ttl("7d") == 604800
    assert parse_ttl("45m") == 45 * 60
    assert parse_ttl("12h") == 12 * 3600
    assert parse_ttl("30d") == 30 * 86400
    assert parse_ttl("365d") == 365 * 86400
    assert parse_ttl("forever") is None
    assert parse_ttl(" Forever ") is None
    for bad in ("", "90", "w", "0m", "366d", "abc", "1h30m", "-1h", "99999d"):
        with pytest.raises(ValueError):
            parse_ttl(bad)


# --- API: TTL behaviour --------------------------------------------------------

def test_custom_ttl_reflected_in_expires_at(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    r = _create(client, {"ttl": "45m"})
    assert r.status_code == 200
    from datetime import datetime

    expires = datetime.fromisoformat(r.json()["expires_at"].replace("Z", "+00:00"))
    delta = expires - datetime.now(tz=expires.tzinfo)
    assert timedelta(minutes=44) < delta <= timedelta(minutes=45)


def test_forever_room_semantics(client, env):
    operator_login(client, "admin", "cliproom-dev-admin")
    r = _create(client, {"ttl": "forever"})
    assert r.status_code == 200
    room_id = r.json()["room_id"]
    assert r.json()["expires_at"] is None

    # member can use the room; metadata exposes null expiry
    token, member = join(client, room_id, "eternal")
    assert client.get(f"/api/rooms/{room_id}").json()["expires_at"] is None

    # activity does NOT conjure an expiry
    assert (
        client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "still here"},
            headers={"X-Member-Token": token},
        ).status_code
        == 200
    )

    # the sweeper never deletes a forever room
    from app.config import get_settings
    from app.db import session_factory
    from app.models import Room
    from app.sweeper import run_sweep

    db = session_factory()()
    row = db.get(Room, room_id)
    assert row.expires_at is None and row.ttl_seconds is None
    db.close()
    run_sweep(get_settings())
    assert client.get(f"/api/rooms/{room_id}").status_code == 200

    # admin can still terminate it manually anytime
    db = session_factory()()
    room_uuid = db.get(Room, room_id).room_uuid
    db.close()
    assert (
        client.delete(
            f"/api/admin/rooms/{room_uuid}", headers=_auth_headers()
        ).status_code
        == 200
    )
    assert client.get(f"/api/rooms/{room_id}").status_code == 404


def test_forever_room_counts_as_guests_active_room(client):
    operator_login(client, "guest", "cliproom-dev-guest")
    assert _create(client, {"ttl": "forever"}).status_code == 200
    r = _create(client, {"ttl": "1h"})
    assert r.status_code == 409


def test_invalid_ttl_rejected_422(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    for bad in ("90", "0m", "366d", "1h30m"):
        assert _create(client, {"ttl": bad}).status_code == 422, bad


# --- API: per-room upload cap -----------------------------------------------------

def _upload(client, room_id, token, name, size):
    return client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": (name, io.BytesIO(b"x" * size), "application/octet-stream")},
        headers={"X-Member-Token": token},
    )


def test_per_room_upload_cap_enforced(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = _create(client, {"ttl": "1h", "max_file_mb": 1}).json()["room_id"]
    token, _ = join(client, room_id, "alice")

    ok = _upload(client, room_id, token, "small.txt", 1024)
    assert ok.status_code == 200

    too_big = _upload(client, room_id, token, "big.txt", int(1.5 * 1024 * 1024))
    assert too_big.status_code == 413
    assert "room's 1 MB" in too_big.json()["detail"]


def test_room_without_cap_uses_global(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = _create(client, {"ttl": "1h"}).json()["room_id"]
    token, _ = join(client, room_id, "alice")
    # global dev default is 10 MB → 2 MB passes
    assert _upload(client, room_id, token, "mid.txt", 2 * 1024 * 1024).status_code == 200


def test_per_room_cap_validation(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    assert _create(client, {"ttl": "1h", "max_file_mb": 0}).status_code == 422
    r = _create(client, {"ttl": "1h", "max_file_mb": 999})  # > global 10
    assert r.status_code == 422
    assert "global cap" in r.text
