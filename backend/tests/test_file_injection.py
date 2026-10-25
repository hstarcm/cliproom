"""File-injection hardening (upload allowlist bypass vectors + serving):

- double extensions (evil.php.txt) are stored but served with the CANONICAL
  mime of the allowlisted extension, as attachment — inert bytes
- trailing dots/spaces, query-suffixed or extensionless names → 415
- control chars / null bytes in filenames sanitized before storage and can
  never reach response headers
- the client-declared Content-Type is never used to serve a download
"""

from __future__ import annotations

import io

from tests.conftest import join, operator_login


def _setup(client):
    operator_login(client, "admin", "cliproom-dev-admin")
    room_id = client.post(
        "/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"}
    ).json()["room_id"]
    token, _ = join(client, room_id, "auditor")
    return room_id, token


def _upload(client, room_id, token, name, mime="text/plain"):
    return client.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": (name, io.BytesIO(b"payload"), mime)},
        headers={"X-Member-Token": token},
    )


def test_bypass_extensions_rejected(client):
    room_id, token = _setup(client)
    for name in (
        "evil.exe.",          # trailing dot → empty ext
        "evil.exe ",          # trailing space
        "evil.exe?",          # query suffix garbage
        "shell.php5",         # unlisted extension
        "archive.tar.gz",     # gz not allowlisted
        "noextension",        # bare
        ".htaccess",          # dotfile, no ext
    ):
        r = _upload(client, room_id, token, name)
        assert r.status_code == 415, name


def test_double_extension_inert(client):
    room_id, token = _setup(client)
    # allowed by extension (.txt); must be served as text/plain attachment —
    # never as the client-declared type, never executed
    r = _upload(client, room_id, token, "evil.php.txt", mime="application/x-httpd-php")
    assert r.status_code == 200
    fid = r.json()["file"]["file_id"]
    dl = client.get(f"/api/rooms/{room_id}/files/{fid}")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("text/plain")  # canonical, not x-httpd-php
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.headers["x-content-type-options"] == "nosniff"


def test_client_mime_never_used_for_serving(client):
    room_id, token = _setup(client)
    r = _upload(client, room_id, token, "page.txt", mime="text/html")
    assert r.status_code == 200
    dl = client.get(f"/api/rooms/{room_id}/files/{r.json()['file']['file_id']}")
    assert dl.headers["content-type"].startswith("text/plain")  # canonical for .txt
    assert dl.headers["content-disposition"].startswith("attachment")


def test_control_chars_and_null_bytes_sanitized(client):
    room_id, token = _setup(client)
    for name in (
        "nul\x00byte.txt",
        "cr\r\nheader-inject.txt",
        "bell\x07.txt",
    ):
        r = _upload(client, room_id, token, name)
        assert r.status_code == 200, repr(name)
        stored = r.json()["file"]["name"]
        assert all(ord(c) >= 0x20 and ord(c) != 0x7F for c in stored), repr(stored)
        dl = client.get(f"/api/rooms/{room_id}/files/{r.json()['file']['file_id']}")
        assert dl.status_code == 200
        disp = dl.headers["content-disposition"]
        assert "\r" not in disp and "\n" not in disp and "\x00" not in disp


def test_canonical_mime_map_covers_allowlist(client):
    from app.routers.rooms import CANONICAL_MIME
    from app.config import get_settings

    assert set(CANONICAL_MIME) == get_settings().allowed_ext_set
    assert CANONICAL_MIME["jpg"] == "image/jpeg"
    assert CANONICAL_MIME["zip"] == "application/zip"
