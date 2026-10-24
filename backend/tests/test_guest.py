"""FR-7: guest constraints — one active room (409), delete-own-room only,
recreate after delete, 403 on admin routes and other rooms."""

from tests.conftest import join, operator_login


def _login(client, user, password):
    client.cookies.clear()
    client.headers.pop("Cookie", None)
    return operator_login(client, user, password)


def _create(client):
    return client.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"})


def test_guest_one_active_room_then_409(client):
    _login(client, "guest", "cliproom-dev-guest")
    r1 = _create(client)
    assert r1.status_code == 200
    room = r1.json()
    assert len(room["room_id"]) >= 22
    assert room["share_url"].endswith(f"/r/{room['room_id']}")

    r2 = _create(client)
    assert r2.status_code == 409
    assert "delete" in r2.json()["detail"].lower()


def test_guest_deletes_own_room_members_get_404_then_recreate(client):
    _login(client, "guest", "cliproom-dev-guest")
    room_id = _create(client).json()["room_id"]
    token, member = join(client, room_id, "visitor")
    assert member["name"] == "visitor"

    rooms = client.get("/api/admin/rooms")
    assert rooms.status_code == 403  # guest blocked from admin dashboard

    # guest deletes its own room via the operator route (room_uuid unknown to
    # guest — it only knows room_id; fetch uuid via DB)
    from app.db import session_factory
    from app.models import Room

    db = session_factory()()
    room_uuid = db.query(Room).filter(Room.room_id == room_id).one().room_uuid
    db.close()

    r = client.delete(f"/api/rooms/{room_uuid}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    # members immediately get 404
    assert client.get(f"/api/rooms/{room_id}").status_code == 404

    # recreate works after delete
    assert _create(client).status_code == 200


def test_guest_cannot_delete_admin_room(client):
    _login(client, "admin", "cliproom-dev-admin")
    admin_room = _create(client).json()["room_id"]

    from app.db import session_factory
    from app.models import Room

    db = session_factory()()
    room_uuid = db.query(Room).filter(Room.room_id == admin_room).one().room_uuid
    db.close()

    _login(client, "guest", "cliproom-dev-guest")
    r = client.delete(f"/api/rooms/{room_uuid}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 403
    assert client.get(f"/api/rooms/{admin_room}").status_code == 200  # untouched


def test_unauthenticated_create_401(client):
    assert _create(client).status_code == 401
