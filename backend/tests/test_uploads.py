"""FR-13/SR-5 + FR-15/SR-2: upload validation (413/415), attachment serving,
delete-own-only, hashed tokens, constant-time compare."""

from __future__ import annotations

import io

from tests.conftest import join, member_token, operator_login


def _setup_room(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    r = client.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"})
    room_id = r.json()["room_id"]
    token_a, a = join(client, room_id, "alice")
    token_b, b = join(client, room_id, "bob")
    return room_id, token_a, a, token_b, b


def test_upload_size_cap_413(client):
    room_id, token_a, _, _, _ = _setup_room(client)
    big = io.BytesIO(b"x" * (10 * 1024 * 1024 + 1))
    r = client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": ("big.txt", big, "text/plain")},
        headers={"X-Member-Token": token_a},
    )
    assert r.status_code == 413
    assert "limit" in r.json()["detail"].lower()


def test_upload_disallowed_type_415(client):
    room_id, token_a, _, _, _ = _setup_room(client)
    r = client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": ("evil.svg", io.BytesIO(b"<svg/>"), "image/svg+xml")},
        headers={"X-Member-Token": token_a},
    )
    assert r.status_code == 415
    r = client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers={"X-Member-Token": token_a},
    )
    assert r.status_code == 415


def test_upload_allowed_and_download_attachment_headers(client):
    room_id, token_a, _, _, _ = _setup_room(client)
    r = client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        headers={"X-Member-Token": token_a},
    )
    assert r.status_code == 200
    item = r.json()
    assert item["kind"] == "file"
    assert item["file"]["name"] == "notes.txt"

    dl = client.get(f"/api/rooms/{room_id}/files/{item['file']['file_id']}")
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.headers["x-content-type-options"] == "nosniff"


def test_delete_own_200_other_403_missing_403(client):
    room_id, token_a, _, token_b, _ = _setup_room(client)
    item = client.post(
        f"/api/rooms/{room_id}/items/text",
        json={"content": "hello"},
        headers={"X-Member-Token": token_a},
    ).json()

    # missing token → 403
    assert (
        client.delete(f"/api/rooms/{room_id}/items/{item['item_id']}").status_code == 403
    )
    # other member's token → 403
    assert (
        client.delete(
            f"/api/rooms/{room_id}/items/{item['item_id']}",
            headers={"X-Member-Token": token_b},
        ).status_code
        == 403
    )
    # author → 200
    assert (
        client.delete(
            f"/api/rooms/{room_id}/items/{item['item_id']}",
            headers={"X-Member-Token": token_a},
        ).status_code
        == 200
    )
    # gone
    assert client.get(f"/api/rooms/{room_id}").json()["item_count"] == 0


def test_member_token_hashed_and_constant_time():
    from app.security import hash_member_token, tokens_match

    token = member_token()
    h = hash_member_token(token)
    assert h != token  # never the raw token
    assert len(h) == 64  # sha256 hex
    assert tokens_match(token, h)
    assert not tokens_match(token[:-1] + ("0" if token[-1] != "0" else "1"), h)
