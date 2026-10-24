"""FR-3/FR-4 + SR-3/SR-7: auth, sessions, generic errors, login rate limit
(with injected clock), role resolution, logout invalidation."""

from __future__ import annotations

from app.ratelimit import RateLimiter


def _cookie_attrs(client):
    r = client.post(
        "/api/admin/login", json={"username": "admin", "password": "cliproom-dev-admin"}
    )
    set_cookie = r.headers["set-cookie"]
    return r, set_cookie


def test_login_success_sets_secure_cookie_with_role(client):
    r, set_cookie = _cookie_attrs(client)
    assert r.status_code == 200
    assert r.json() == {"role": "admin"}
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_login_wrong_password_generic_error(client):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"  # generic, no enumeration
    # unknown user → identical response
    r2 = client.post("/api/admin/login", json={"username": "nobody", "password": "nope"})
    assert r2.status_code == r.status_code
    assert r2.json() == r.json()


def test_guest_role_resolution(client):
    r = client.post(
        "/api/admin/login", json={"username": "guest", "password": "cliproom-dev-guest"}
    )
    assert r.status_code == 200
    assert r.json() == {"role": "guest"}


def test_logout_invalidates_server_side(client):
    client.post(
        "/api/admin/login", json={"username": "admin", "password": "cliproom-dev-admin"}
    )
    sid = client.cookies.get("cliproom_session")
    client.headers.update({"Cookie": f"cliproom_session={sid}", "X-Requested-With": "fetch"})
    assert client.post("/api/admin/logout").status_code == 200
    # session is dead server-side
    assert client.get("/api/admin/rooms").status_code == 401


def test_login_rate_limit_429_on_6th_attempt(client):
    creds = {"username": "admin", "password": "wrong"}
    for _ in range(5):
        assert client.post("/api/admin/login", json=creds).status_code == 401
    r = client.post("/api/admin/login", json=creds)
    assert r.status_code == 429


def test_rate_limiter_window_reset_with_injected_clock():
    class FakeClock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

    clock = FakeClock()
    limiter = RateLimiter(limit=5, window_seconds=900, clock=clock)
    for _ in range(5):
        assert limiter.hit("login", "1.2.3.4")
    assert not limiter.hit("login", "1.2.3.4")  # 6th blocked
    clock.t += 901  # window passes
    assert limiter.hit("login", "1.2.3.4")  # allowed again
    # other keys unaffected
    assert limiter.hit("login", "5.6.7.8")


def test_operator_routes_require_auth(client):
    assert client.get("/api/admin/rooms").status_code == 401
    assert client.get("/api/health").status_code == 200
