"""Shared fixtures: isolated env, fresh DB, app factory, login helpers."""

from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPROOM_DEV", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("BASE_URL", "http://testserver")

    from app.config import get_settings
    import app.db as dbmod

    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._SessionLocal = None

    from app import wshub
    from app.security import sessions
    from app.wstickets import tickets

    sessions._sessions.clear()
    tickets._tickets.clear()
    wshub.hub._rooms.clear()

    yield tmp_path

    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._SessionLocal = None


@pytest.fixture()
def client(env):
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def operator_login(client: TestClient, username: str, password: str) -> str:
    """Login and attach the session cookie manually (Secure cookies aren't
    replayed by cookie jars over plain http in tests)."""
    r = client.post("/api/admin/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    sid = r.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
    client.cookies.clear()
    client.headers.update({"Cookie": f"cliproom_session={sid}"})
    return r.json()["role"]


def member_token() -> str:
    return secrets.token_hex(32)


def join(client: TestClient, room_id: str, name: str, token: str | None = None):
    token = token or member_token()
    r = client.post(
        f"/api/rooms/{room_id}/join",
        json={"name": name},
        headers={"X-Member-Token": token},
    )
    assert r.status_code == 200, r.text
    return token, r.json()
