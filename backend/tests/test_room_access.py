"""FR-2: room access semantics — unknown room 404 (never 403), known room +
wrong member token → 403."""

from tests.conftest import join, operator_login


def test_unknown_room_404_generic(client):
    for path in (
        "/api/rooms/AAAAAAAAAAAAAAAAAAAAAA42",
        "/api/rooms/AAAAAAAAAAAAAAAAAAAAAA42/items",
        "/api/rooms/AAAAAAAAAAAAAAAAAAAAAA42/join",
    ):
        r = client.get(path) if "join" not in path else client.post(
            path, json={"name": "x"}, headers={"X-Member-Token": "0" * 64}
        )
        assert r.status_code == 404, path
        assert r.json() == {"detail": "Not Found"}  # generic body, no stack info


def test_known_room_wrong_token_403(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = client.post(
        "/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]

    # room itself is reachable
    assert client.get(f"/api/rooms/{room_id}").status_code == 200

    # wrong token on mutating routes → 403 (never 404)
    wrong = "e" * 64
    assert (
        client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "hi"},
            headers={"X-Member-Token": wrong},
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/rooms/{room_id}/ws-ticket", headers={"X-Member-Token": wrong}).status_code
        == 403
    )


def test_join_requires_token_known_room(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = client.post(
        "/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]
    assert client.post(f"/api/rooms/{room_id}/join", json={"name": "x"}).status_code == 403
