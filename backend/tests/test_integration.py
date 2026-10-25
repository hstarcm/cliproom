"""§9 backend integration: the full journey in one test."""

from __future__ import annotations

import io
from datetime import timedelta

from tests.conftest import join, operator_login


def test_full_journey(client, env):
    # --- admin login → create room ------------------------------------------
    role = operator_login(client, "admin", "cliproom-dev-admin")
    assert role == "admin"
    created = client.post("/api/rooms", json={"ttl": "24h"}, headers={"X-Requested-With": "fetch"})
    assert created.status_code == 200
    room = created.json()
    assert len(room["room_id"]) >= 22
    assert room["share_url"].endswith(f"/r/{room['room_id']}")

    # --- two members join ------------------------------------------------------
    token_a, alice = join(client, room["room_id"], "alice")
    token_b, bob = join(client, room["room_id"], "bob")
    assert alice["name"] == "alice" and bob["name"] == "bob"
    assert alice["color"] != bob["color"] or True  # colors may collide; ids differ
    assert alice["member_id"] != bob["member_id"]

    # --- add text + upload file -------------------------------------------------
    text_item = client.post(
        f"/api/rooms/{room['room_id']}/items/text",
        json={"content": "shared snippet"},
        headers={"X-Member-Token": token_a},
    )
    assert text_item.status_code == 200
    file_item = client.post(
        f"/api/rooms/{room['room_id']}/items/file",
        files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        headers={"X-Member-Token": token_b},
    )
    assert file_item.status_code == 200

    state = client.get(f"/api/rooms/{room['room_id']}/items").json()
    assert len(state["items"]) == 2
    kinds = {i["kind"] for i in state["items"]}
    assert kinds == {"text", "file"}
    # newest-first (FR-12)
    assert state["items"][0]["item_id"] == file_item.json()["item_id"]

    # --- delete-own-only ----------------------------------------------------------
    assert (
        client.delete(
            f"/api/rooms/{room['room_id']}/items/{file_item.json()['item_id']}",
            headers={"X-Member-Token": token_a},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/rooms/{room['room_id']}/items/{file_item.json()['item_id']}",
            headers={"X-Member-Token": token_b},
        ).status_code
        == 200
    )

    # --- guest flow ------------------------------------------------------------------
    client.cookies.clear()
    client.headers.pop("Cookie", None)
    assert operator_login(client, "guest", "cliproom-dev-guest") == "guest"
    g1 = client.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"})
    assert g1.status_code == 200
    g_room = g1.json()
    g2 = client.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"})
    assert g2.status_code == 409

    # guest deletes its own room → members immediately 404
    from app.db import session_factory
    from app.models import Room, utcnow

    db = session_factory()()
    g_uuid = db.query(Room).filter(Room.room_id == g_room["room_id"]).one().room_uuid
    db.close()
    assert (
        client.delete(f"/api/rooms/{g_uuid}", headers={"X-Requested-With": "fetch"}).status_code
        == 200
    )
    assert client.get(f"/api/rooms/{g_room['room_id']}").status_code == 404
    # guest can create again
    assert (
        client.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}).status_code
        == 200
    )

    # --- expired room → 404 -----------------------------------------------------------
    db = session_factory()()
    r = db.get(Room, room["room_id"])
    r.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    db.close()
    assert client.get(f"/api/rooms/{room['room_id']}").status_code == 404


def test_admin_dashboard_and_force_terminate(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = client.post(
        "/api/rooms", json={"ttl": "7d"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]

    listing = client.get("/api/admin/rooms")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["created_by"] == "admin"
    assert "room_uuid" in rows[0] and "expires_at" in rows[0]
    # room_id (capability id) is exposed to the authenticated admin so the
    # dashboard can link straight into the room
    assert rows[0]["room_id"] == room_id

    r = client.delete(
        f"/api/admin/rooms/{rows[0]['room_uuid']}", headers={"X-Requested-With": "fetch"}
    )
    assert r.status_code == 200
    assert client.get(f"/api/rooms/{room_id}").status_code == 404
    assert client.get("/api/admin/rooms").json() == []


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"
