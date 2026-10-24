"""FR-8/FR-10: join validation (name bounds), returning member identity,
color determinism."""

from tests.conftest import join, operator_login


def _room(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    return client.post(
        "/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]


def test_name_bounds_422(client):
    room_id = _room(client)
    token = "a" * 64
    for bad in ("", "   ", "x" * 21):
        r = client.post(
            f"/api/rooms/{room_id}/join",
            json={"name": bad},
            headers={"X-Member-Token": token},
        )
        assert r.status_code == 422, bad
    # trimmed to exactly 20 chars is fine
    r = client.post(
        f"/api/rooms/{room_id}/join",
        json={"name": "y" * 20},
        headers={"X-Member-Token": token},
    )
    assert r.status_code == 200


def test_rejoin_same_token_returns_same_identity(client):
    room_id = _room(client)
    token, first = join(client, room_id, "alice")
    _, second = join(client, room_id, "alice", token)
    assert first == second  # member_id, name, color all stable (FR-10)


def test_color_deterministic_from_member_id():
    from app.colors import PALETTE, color_for

    assert color_for("abc") == color_for("abc")
    assert color_for("abc") in PALETTE
    assert len(PALETTE) >= 8
    # palette spreads across members
    assert len({color_for(f"m{i}") for i in range(50)}) > 1


def test_item_shows_author_color(client):
    room_id = _room(client)
    token, member = join(client, room_id, "alice")
    item = client.post(
        f"/api/rooms/{room_id}/items/text",
        json={"content": "hi"},
        headers={"X-Member-Token": token},
    ).json()
    assert item["author"]["name"] == "alice"
    assert item["author"]["color"] == member["color"]


def test_text_clip_bounds_422(client):
    room_id = _room(client)
    token, _ = join(client, room_id, "alice")
    assert (
        client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": ""},
            headers={"X-Member-Token": token},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "x" * 10_001},
            headers={"X-Member-Token": token},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "x" * 10_000},
            headers={"X-Member-Token": token},
        ).status_code
        == 200
    )
