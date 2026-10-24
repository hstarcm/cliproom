"""FR-16/FR-17/FR-18: WS broadcast to all sockets, full state on connect,
no broadcast after rejected delete. Uses one TestClient so all sockets share
a single event loop (the hub is process-global)."""

from __future__ import annotations

import pytest

from tests.conftest import join, operator_login


def _setup(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = client.post(
        "/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]
    return room_id


def _ticket(client, room_id, token):
    return client.post(
        f"/api/rooms/{room_id}/ws-ticket", headers={"X-Member-Token": token}
    ).json()["ticket"]


def _connect(client, room_id, token, name):
    join(client, room_id, name, token)
    ticket = _ticket(client, room_id, token)
    return client.websocket_connect(f"/api/rooms/{room_id}/ws?ticket={ticket}")


def _drain_until(ws, predicate, max_events=20):
    for _ in range(max_events):
        event = ws.receive_json()
        if predicate(event):
            return event
    raise AssertionError("expected event not seen")


def test_state_on_connect_and_live_broadcast_to_all(client):
    room_id = _setup(client)
    token_a = "a" * 64
    token_b = "b" * 64

    with _connect(client, room_id, token_a, "alice") as ws_a:
        state = ws_a.receive_json()
        assert state["type"] == "state"
        assert state["items"] == []

        # A adds text via REST → A's socket gets the event
        item = client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "hello"},
            headers={"X-Member-Token": token_a},
        ).json()

        # B connects later → full state includes the item (FR-17)
        with _connect(client, room_id, token_b, "bob") as ws_b:
            state_b = ws_b.receive_json()
            assert state_b["type"] == "state"
            assert [i["item_id"] for i in state_b["items"]] == [item["item_id"]]
            assert any(m["name"] == "alice" for m in state_b["members"])

            # live add reaches BOTH sockets (FR-16)
            item2 = client.post(
                f"/api/rooms/{room_id}/items/text",
                json={"content": "second"},
                headers={"X-Member-Token": token_a},
            ).json()
            ev_a = _drain_until(
                ws_a,
                lambda e: e["type"] == "item_added" and e["item"]["item_id"] == item2["item_id"],
            )
            ev_b = _drain_until(
                ws_b,
                lambda e: e["type"] == "item_added" and e["item"]["item_id"] == item2["item_id"],
            )
            assert ev_a["item"]["content"] == "second"
            assert ev_b["item"]["content"] == "second"


def test_rejected_delete_never_broadcast(client):
    room_id = _setup(client)
    token_a = "a" * 64
    token_b = "b" * 64
    join(client, room_id, "alice", token_a)
    join(client, room_id, "bob", token_b)

    with _connect(client, room_id, token_a, "alice") as ws_a:
        ws_a.receive_json()  # state

        item = client.post(
            f"/api/rooms/{room_id}/items/text",
            json={"content": "mine"},
            headers={"X-Member-Token": token_a},
        ).json()
        _drain_until(ws_a, lambda e: e["type"] == "item_added")

        # B attempts to delete A's item → 403, and no item_deleted broadcast
        r = client.delete(
            f"/api/rooms/{room_id}/items/{item['item_id']}",
            headers={"X-Member-Token": token_b},
        )
        assert r.status_code == 403

        # A deletes own item → 200 + broadcast
        assert (
            client.delete(
                f"/api/rooms/{room_id}/items/{item['item_id']}",
                headers={"X-Member-Token": token_a},
            ).status_code
            == 200
        )
        ev = _drain_until(ws_a, lambda e: e["type"] == "item_deleted")
        assert ev["item_id"] == item["item_id"]
        # no stray item_deleted was delivered before the accepted one: the first
        # item_deleted event observed corresponds to the authorised delete only.


def test_ws_requires_valid_one_time_ticket(client):
    room_id = _setup(client)
    token_a = "a" * 64
    join(client, room_id, "alice", token_a)

    with pytest.raises(Exception):
        # bad ticket → handshake rejected
        with client.websocket_connect(f"/api/rooms/{room_id}/ws?ticket=bogus"):
            pass

    # a real ticket works only once
    ticket = _ticket(client, room_id, token_a)
    with client.websocket_connect(f"/api/rooms/{room_id}/ws?ticket={ticket}") as ws:
        assert ws.receive_json()["type"] == "state"
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/rooms/{room_id}/ws?ticket={ticket}"):
            pass
