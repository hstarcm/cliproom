"""Adversarial security + concurrency audit against the LIVE compose stack
(through nginx — the real attack path).

Restart the api between limit phases (fresh per-process rate limiters; the
DB persists):

  docker compose restart api && sleep 6
  backend/.venv/Scripts/python scripts/security_audit.py <phase>

Phases: auth, rooms, concurrency, limit_login, limit_upload, limit_ws, hygiene
"""
from __future__ import annotations

import asyncio
import io
import json
import secrets
import subprocess
import sys

import httpx
import websockets

BASE = "http://localhost:8080"
WS_BASE = "ws://localhost:8080"
ADMIN = {"username": "admin", "password": "cliproom-dev-admin"}
GUEST = {"username": "guest", "password": "cliproom-dev-guest"}

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def tok() -> str:
    return secrets.token_hex(32)


def login(http: httpx.Client, creds: dict) -> dict:
    r = http.post("/api/admin/login", json=creds, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, r.text
    sid = r.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
    return {"X-Requested-With": "fetch", "Cookie": f"cliproom_session={sid}"}


def create_room(http: httpx.Client, op: dict, **body) -> dict:
    r = http.post("/api/rooms", json={"ttl": "1h", **body}, headers=op)
    assert r.status_code == 200, r.text
    return r.json()


def join(http: httpx.Client, room_id: str, name: str, token: str) -> dict:
    r = http.post(
        f"/api/rooms/{room_id}/join", json={"name": name}, headers={"X-Member-Token": token}
    )
    assert r.status_code == 200, r.text
    return r.json()


def upload(http: httpx.Client, room_id: str, token: str, name: str, data: bytes, mime="text/plain"):
    return http.post(
        f"/api/rooms/{room_id}/items/file",
        files={"file": (name, io.BytesIO(data), mime)},
        headers={"X-Member-Token": token},
    )


# ------------------------------------------------------------------ phases --

def phase_auth() -> None:
    """Lives within the 5-logins/15min/IP budget: 2 enumeration probes +
    2 admin logins + 1 guest login = exactly 5."""
    print("== AUTH / SESSION / CSRF / PRIVILEGES ==")
    http = httpx.Client(base_url=BASE, timeout=15)

    # attempts 1-2: enumeration probes (identical bodies)
    r1 = http.post("/api/admin/login", json={"username": "nosuchuser", "password": "x"},
                   headers={"X-Requested-With": "fetch"})
    r2 = http.post("/api/admin/login", json={"username": "admin", "password": "wrongpw"},
                   headers={"X-Requested-With": "fetch"})
    check("no user enumeration (identical 401 bodies)",
          r1.status_code == r2.status_code == 401 and r1.json() == r2.json())

    forged_ok = True
    for bad in ("deadbeef", "z" * 64, "'; DROP TABLE rooms;--"):
        if http.get("/api/admin/rooms", headers={"Cookie": f"cliproom_session={bad}"}).status_code != 401:
            forged_ok = False
    check("forged/garbage/SQLi session cookies rejected (401)", forged_ok)

    # attempt 3: cookie hardening + CSRF + room ops on one session
    r = http.post("/api/admin/login", json=ADMIN, headers={"X-Requested-With": "fetch"})
    setc = r.headers["set-cookie"].lower()
    check("session cookie HttpOnly+Secure+SameSite=Lax",
          all(x in setc for x in ("httponly", "secure", "samesite=lax")))
    check("login returns role only", r.json() == {"role": "admin"})
    sid = r.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
    op = {"X-Requested-With": "fetch", "Cookie": f"cliproom_session={sid}"}
    nohdr = {"Cookie": op["Cookie"]}
    check("CSRF: create room without X-Requested-With → 403",
          http.post("/api/rooms", json={"ttl": "1h"}, headers=nohdr).status_code == 403)
    check("CSRF: delete room without X-Requested-With → 403",
          http.delete("/api/rooms/whatever", headers=nohdr).status_code == 403)
    admin_room = create_room(http, op)

    # attempt 4: guest session — privilege separation
    guest_r = http.post("/api/admin/login", json=GUEST, headers={"X-Requested-With": "fetch"})
    check("guest login resolves role", guest_r.status_code == 200 and guest_r.json() == {"role": "guest"})
    gsid = guest_r.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
    guest = {"X-Requested-With": "fetch", "Cookie": f"cliproom_session={gsid}"}
    check("guest blocked from admin dashboard (403)",
          http.get("/api/admin/rooms", headers={"Cookie": guest["Cookie"]}).status_code == 403)

    uuids = {r["room_uuid"]: r for r in http.get("/api/admin/rooms", headers=op).json()}
    admin_uuid = next(u for u, r in uuids.items() if r["created_by"] == "admin")
    check("guest cannot terminate an admin room (403)",
          http.delete(f"/api/rooms/{admin_uuid}", headers=guest).status_code == 403)
    check("admin room untouched after guest attempt",
          http.get(f"/api/rooms/{admin_room['room_id']}").status_code == 200)

    http.cookies.clear()  # must be truly anonymous
    # CSRF runs before auth on this route: with the custom header present,
    # a cookie-less create is properly 401 (AC1); without it, 403 (SR-7)
    no_csrf = http.post("/api/rooms", json={"ttl": "1h"})
    with_csrf = http.post("/api/rooms", json={"ttl": "1h"}, headers={"X-Requested-With": "fetch"})
    check("unauthenticated create room → 401 (and 403 when the CSRF header is missing)",
          no_csrf.status_code == 403 and with_csrf.status_code == 401,
          f"no_csrf={no_csrf.status_code} with_csrf={with_csrf.status_code}")

    # attempt 5: fresh admin session for the logout-invalidation proof
    op2_sid = http.post("/api/admin/login", json=ADMIN, headers={"X-Requested-With": "fetch"})
    sid2 = op2_sid.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
    op2 = {"X-Requested-With": "fetch", "Cookie": f"cliproom_session={sid2}"}
    check("logout ok", http.post("/api/admin/logout", headers=op2).status_code == 200)
    check("session dead after logout (server-side invalidation)",
          http.get("/api/admin/rooms", headers=op2).status_code == 401)

    check("agent endpoint: no token → 403",
          http.post("/api/agent/on-alert", json={"alerts": []}).status_code == 403)
    check("agent endpoint: wrong token → 403",
          http.post("/api/agent/on-alert", json={"alerts": []},
                    headers={"X-Agent-Token": tok()}).status_code == 403)


def nosniff_ok(headers) -> bool:
    """App middleware and nginx BOTH set the security headers (defense in
    depth — the api is also reachable directly on :8000); httpx joins
    duplicates, so compare each comma-separated value."""
    return all_values(headers, "x-content-type-options", "nosniff")


def all_values(headers, key: str, expected: str) -> bool:
    vals = [v.strip() for v in headers.get(key, "").split(",") if v.strip()]
    return bool(vals) and all(v == expected for v in vals)


def phase_rooms() -> None:
    print("== ROOMS: capability model, injection, upload hardening ==")
    http = httpx.Client(base_url=BASE, timeout=20)
    op = login(http, ADMIN)
    room = create_room(http, op)
    rid = room["room_id"]
    check("room ID ≥22 chars base62",
          len(rid) >= 22 and rid.isascii() and rid.isalnum())

    # ---- capability 404 semantics ----
    unknown = http.get("/api/rooms/AAAAAAAAAAAAAAAAAAAAAA99")
    term_room = create_room(http, op)
    uuids = {r["room_uuid"]: r for r in http.get("/api/admin/rooms", headers=op).json()}
    tu = next(u for u, r in uuids.items() if r["room_uuid"] and r["item_count"] == 0)
    http.delete(f"/api/admin/rooms/{tu}", headers=op)
    deleted = http.get(f"/api/rooms/{term_room['room_id']}")
    check("unknown vs deleted room: identical generic 404",
          unknown.status_code == deleted.status_code == 404 and unknown.json() == deleted.json() == {"detail": "Not Found"})

    # ---- SQL injection surfaces ----
    sqli_ok = True
    for payload in ("' OR '1'='1", "x'; DROP TABLE rooms;--", "1 UNION SELECT 1"):
        p1 = http.get(f"/api/rooms/{payload}")
        # a payload *name* is legal data (1-20 chars) — must be stored
        # verbatim via parameterised queries, never interpreted
        p2 = http.post(f"/api/rooms/{rid}/join", json={"name": payload[:20]},
                       headers={"X-Member-Token": tok()})
        if p1.status_code != 404 or p2.status_code != 200 or p2.json()["name"] != payload[:20]:
            sqli_ok = False
    still = http.get(f"/api/rooms/{rid}")
    check("SQLi payloads on room_id/name treated as data (param queries; DB intact)",
          sqli_ok and still.status_code == 200)

    # ---- join validation ----
    ta = tok()
    bad_names_ok = all(
        http.post(f"/api/rooms/{rid}/join", json={"name": n},
                  headers={"X-Member-Token": ta}).status_code == 422
        for n in ("", "   ", "x" * 21)
    )
    check("name bounds enforced (0/21 chars → 422)", bad_names_ok)
    join(http, rid, "alice", ta)
    tb = tok()
    join(http, rid, "bob", tb)

    # ---- cross-room token ----
    other = create_room(http, op)
    check("room-A token cannot act in room B (403)",
          http.post(f"/api/rooms/{other['room_id']}/items/text", json={"content": "hi"},
                    headers={"X-Member-Token": ta}).status_code == 403)

    # ---- stored XSS payload is data, not markup ----
    xss = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    r = http.post(f"/api/rooms/{rid}/items/text", json={"content": xss},
                  headers={"X-Member-Token": ta})
    check("XSS payload stored/returned as JSON data only",
          r.status_code == 200 and r.headers["content-type"].startswith("application/json")
          and r.json()["content"] == xss)

    # ---- upload hardening ----
    bad_ext = all(upload(http, rid, ta, n, b"x").status_code == 415 for n in
                  ("e.exe", "e.svg", "e.php", "e.sh", "evil.php.txt." + "bin", "noext"))
    check("deny-by-default extensions (.exe/.svg/.php/.sh/noext → 415)", bad_ext)

    trav = upload(http, rid, ta, "../../evil.txt", b"pwn")
    trav2 = upload(http, rid, ta, "..\\..\\evil2.txt", b"pwn")
    stored = trav.json().get("file", {}).get("name", "")
    dl_t2 = http.get(f"/api/rooms/{rid}/files/{trav2.json()['file']['file_id']}")
    disp = dl_t2.headers.get("content-disposition", "")
    check("path traversal neutralised (basename strips forward slashes; "
          "backslashes never reach the filesystem — files stored under uuid "
          "ids — and are stripped from the download header)",
          trav.status_code == trav2.status_code == 200
          and stored == "evil.txt" and "/" not in stored
          and "\\" not in disp and "\r" not in disp and "\n" not in disp,
          f"stored={stored!r} disp={disp[:80]!r}")

    ls = subprocess.run(["docker", "exec", "cliproom-api-1", "sh", "-c",
                         "find /data/files -mindepth 1 -maxdepth 1 \\( -name 'evil*' ! -type d \\) -o -mindepth 1 -maxdepth 1 ! -type d | wc -l"],
                        capture_output=True, text=True)
    check("no traversal file written outside room dirs", ls.stdout.strip() == "0", ls.stdout.strip())

    crlf = upload(http, rid, ta, "a\r\nX-Injected: yes.txt", b"x")
    dl = http.get(f"/api/rooms/{rid}/files/{crlf.json()['file']['file_id']}")
    disp = dl.headers.get("content-disposition", "")
    check("CRLF header injection neutralised in Content-Disposition",
          dl.status_code == 200 and "\r" not in disp and "\n" not in disp
          and nosniff_ok(dl.headers)
          and "x-injected" not in {k.lower() for k in dl.headers.keys()},
          f"status={dl.status_code} disp={disp[:90]!r}")

    spoof = upload(http, rid, ta, "page.txt", b"<html><script>alert(3)</script></html>", mime="text/html")
    dl2 = http.get(f"/api/rooms/{rid}/files/{spoof.json()['file']['file_id']}")
    check("HTML-content file served as attachment + nosniff (no inline render)",
          dl2.status_code == 200 and dl2.headers["content-disposition"].startswith("attachment")
          and nosniff_ok(dl2.headers),
          f"status={dl2.status_code} disp={dl2.headers.get('content-disposition', '-')[:60]!r}")

    # ---- IDOR: cross-room file access ----
    f = upload(http, rid, ta, "secret.txt", b"room A secret")
    fid = f.json()["file"]["file_id"]
    tc = tok()
    join(http, other["room_id"], "mallory", tc)
    check("IDOR: room-B member cannot fetch room-A file by id (404)",
          http.get(f"/api/rooms/{other['room_id']}/files/{fid}").status_code == 404)

    # ---- delete-own-only ----
    item = http.post(f"/api/rooms/{rid}/items/text", json={"content": "mine"},
                     headers={"X-Member-Token": ta}).json()
    check("no token → 403",
          http.delete(f"/api/rooms/{rid}/items/{item['item_id']}").status_code == 403)
    check("other member → 403",
          http.delete(f"/api/rooms/{rid}/items/{item['item_id']}",
                      headers={"X-Member-Token": tb}).status_code == 403)
    check("author → 200",
          http.delete(f"/api/rooms/{rid}/items/{item['item_id']}",
                      headers={"X-Member-Token": ta}).status_code == 200)

    # ---- ws-ticket: single-use + room binding ----
    t1 = http.post(f"/api/rooms/{rid}/ws-ticket", headers={"X-Member-Token": ta}).json()["ticket"]
    check("ticket bound to its room (other room ws rejected)",
          _ws_rejected(f"{WS_BASE}/api/rooms/{other['room_id']}/ws?ticket={t1}"))
    check("ticket single-use",
          _ws_accepted_once(f"{WS_BASE}/api/rooms/{rid}/ws?ticket={t1}"))

    # ---- token stored hashed ----
    q = subprocess.run(["docker", "exec", "cliproom-api-1", "python", "-c",
                        "from app.config import get_settings; from app.db import init_engine, session_factory;"
                        "init_engine(get_settings().db_path);"
                        "from app.models import Member; s=session_factory()();"
                        "import sys; sys.stdout.write(str(s.query(Member).filter(Member.token_hash==%r).count()))" % __import__("hashlib").sha256(ta.encode()).hexdigest()],
                       capture_output=True, text=True)
    check("member token stored as SHA-256 hash (raw never persisted)", q.stdout.strip() == "1")


def _ws_rejected(url: str) -> bool:
    try:
        asyncio.run(websockets.connect(url).__aenter__())
        return False
    except Exception:
        return True


def _ws_accepted_once(url: str) -> bool:
    async def go():
        try:
            async with websockets.connect(url) as ws:
                await asyncio.wait_for(ws.recv(), 5)  # state
            async with websockets.connect(url):
                pass
            return False  # reuse accepted → bad
        except Exception:
            return True  # second connect rejected → good
    return asyncio.run(go())


def phase_concurrency() -> None:
    print("== CONCURRENCY: 5 simultaneous members ==")
    try:
        asyncio.run(_concurrency())
    except Exception:
        print(f"  DIAG received={_DIAG.get('received')} closed={_DIAG.get('closed')}")
        raise


_DIAG: dict = {}


async def _concurrency() -> None:
    http = httpx.Client(base_url=BASE, timeout=30)
    op = login(http, ADMIN)
    room = create_room(http, op)
    rid = room["room_id"]

    names = ["ana", "ben", "cy", "dee", "eli"]
    tokens = {n: tok() for n in names}
    for n in names:
        join(http, rid, n, tokens[n])

    # one background reader per socket keeps answering server pings even while
    # the main task is busy with HTTP bursts — exactly like the browser client
    queues: dict[str, asyncio.Queue] = {}
    closed: dict[str, str] = {}
    received: dict[str, int] = {}
    _DIAG["received"] = received
    _DIAG["closed"] = closed

    async def pump(name: str, ws) -> None:
        q: asyncio.Queue = asyncio.Queue()
        queues[name] = q
        received[name] = 0
        try:
            async for msg in ws:
                received[name] += 1
                q.put_nowait(json.loads(msg))
        except Exception as exc:
            closed[name] = f"{type(exc).__name__}: {getattr(getattr(exc, 'rcvd', None), 'code', None)}"
        finally:
            q.put_nowait({"type": "__pump_end__"})

    async def connect(n):
        t = http.post(f"/api/rooms/{rid}/ws-ticket", headers={"X-Member-Token": tokens[n]}).json()["ticket"]
        ws = await websockets.connect(f"{WS_BASE}/api/rooms/{rid}/ws?ticket={t}")
        state = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert state["type"] == "state"
        return n, ws

    conns = await asyncio.gather(*[connect(n) for n in names])
    pumps = [asyncio.create_task(pump(n, ws)) for n, ws in conns]
    sockets = [ws for _, ws in conns]
    await asyncio.sleep(0.2)  # let pumps take over the read loops

    seen_by_name: dict[str, set] = {n: set() for n in names}

    async def drain(name: str, wanted: set[str], timeout=15.0, label=""):
        seen = seen_by_name[name]  # cumulative: events are consumed once per socket
        q = queues[name]
        end = asyncio.get_event_loop().time() + timeout
        while seen != wanted:
            remaining = end - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise AssertionError(
                    f"drain{label} {name}: missing {len(wanted - seen)} of {len(wanted)}"
                )
            ev = await asyncio.wait_for(q.get(), remaining)
            if ev.get("type") == "__pump_end__":
                raise AssertionError(f"drain{label} {name}: socket closed early")
            if ev.get("type") == "item_added":
                seen.add(ev["item"]["item_id"])
            elif ev.get("type") == "item_deleted":
                seen.discard(ev["item_id"])
        return seen

    # 5 concurrent text clips (5 separate connections for real parallelism)
    async def add_text(n):
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as ac:
            r = await ac.post(f"/api/rooms/{rid}/items/text",
                              json={"content": f"clip from {n}"},
                              headers={"X-Member-Token": tokens[n]})
            return r.status_code, r.json().get("item_id")

    added = await asyncio.gather(*[add_text(n) for n in names])
    check("5 concurrent text adds all 200", all(s == 200 for s, _ in added))
    ids = {iid for _, iid in added}
    per_socket = await asyncio.gather(*[drain(n, ids, label="clips") for n in names])
    check("every one of 5 sockets received all 5 clips (no loss/dup)",
          all(ps == ids for ps in per_socket))

    # 5 concurrent uploads
    async def up(n):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as ac:
            r = await ac.post(f"/api/rooms/{rid}/items/file",
                              files={"file": (f"{n}.txt", io.BytesIO(f"data-{n}".encode() * 512), "text/plain")},
                              headers={"X-Member-Token": tokens[n]})
            return r.status_code, r.json().get("item_id")

    ups = await asyncio.gather(*[up(n) for n in names])
    check("5 concurrent uploads all 200", all(s == 200 for s, _ in ups))
    upids = {iid for _, iid in ups}
    per_socket = await asyncio.gather(*[drain(n, ids | upids, label="uploads") for n in names])
    check("every socket saw all 5 uploads broadcast", all(ps == ids | upids for ps in per_socket))

    # presence shows all five
    state = http.get(f"/api/rooms/{rid}/items").json()
    check("presence lists all 5 members",
          {m["name"] for m in state["members_present"]} == set(names))

    # concurrent own-item deletes
    async def deleter(n, iid):
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as ac:
            r = await ac.delete(f"/api/rooms/{rid}/items/{iid}",
                                headers={"X-Member-Token": tokens[n]})
            return r.status_code

    dels = await asyncio.gather(*[deleter(n, iid) for n, (_, iid) in zip(names, ups)])
    check("5 concurrent own-item deletes all 200", all(s == 200 for s in dels))
    per_socket = await asyncio.gather(*[drain(n, ids, label="deletes") for n in names])
    check("every socket saw all 5 deletions (final state = 5 text clips)",
          all(ps == ids for ps in per_socket))

    final = http.get(f"/api/rooms/{rid}/items").json()
    check("final REST state consistent (5 clips, 0 files)",
          len(final["items"]) == 5 and all(i["kind"] == "text" for i in final["items"]))

    for ws in sockets:
        await ws.close()
    for p in pumps:
        p.cancel()


def phase_limit_login() -> None:
    print("== RATE LIMIT: login 5/15min/IP ==")
    http = httpx.Client(base_url=BASE, timeout=15)
    codes = [http.post("/api/admin/login", json={"username": "admin", "password": "wrong"},
                       headers={"X-Requested-With": "fetch"}).status_code for _ in range(5)]
    sixth = http.post("/api/admin/login", json={"username": "admin", "password": "wrong"},
                      headers={"X-Requested-With": "fetch"}).status_code
    check("5 failures → 401, 6th → 429", codes == [401] * 5 and sixth == 429)


def phase_limit_upload() -> None:
    print("== RATE LIMIT: uploads 30/h/IP + size caps ==")
    http = httpx.Client(base_url=BASE, timeout=30)
    op = login(http, ADMIN)
    room = create_room(http, op)
    rid = room["room_id"]
    t = tok()
    join(http, rid, "burster", t)
    codes = [upload(http, rid, t, f"f{i}.txt", b"x").status_code for i in range(30)]
    over = upload(http, rid, t, "f30.txt", b"x").status_code
    check("30 uploads ok, 31st → 429", all(c == 200 for c in codes) and over == 429)

    # size caps still enforced after limiter exhausted? (different failure mode)
    big = upload(http, rid, t, "huge.txt", b"x" * (11 * 1024 * 1024))
    check("429 (rate) precedes 413 handling for over-limit burst", big.status_code == 429)


def phase_limit_ws() -> None:
    print("== RATE LIMIT: ≤10 WS connections/IP ==")
    asyncio.run(_limit_ws())


async def _limit_ws() -> None:
    http = httpx.Client(base_url=BASE, timeout=15)
    op = login(http, ADMIN)
    room = create_room(http, op)
    rid = room["room_id"]
    t = tok()
    join(http, rid, "wswarm", t)

    socks = []
    accepted = 0
    for _ in range(10):
        ticket = http.post(f"/api/rooms/{rid}/ws-ticket", headers={"X-Member-Token": t}).json()["ticket"]
        try:
            ws = await websockets.connect(f"{WS_BASE}/api/rooms/{rid}/ws?ticket={ticket}")
            await asyncio.wait_for(ws.recv(), 5)
            socks.append(ws)
            accepted += 1
        except Exception:
            break
    check("up to 10 WS connections accepted", accepted == 10)
    ticket = http.post(f"/api/rooms/{rid}/ws-ticket", headers={"X-Member-Token": t}).json()["ticket"]
    try:
        async with websockets.connect(f"{WS_BASE}/api/rooms/{rid}/ws?ticket={ticket}"):
            ok11 = False
    except Exception:
        ok11 = True
    check("11th WS connection rejected", ok11)
    for ws in socks:
        await ws.close()


def phase_hygiene() -> None:
    print("== HEADERS / CORS / ERROR HANDLING / LOG HYGIENE ==")
    http = httpx.Client(base_url=BASE, timeout=15)
    endpoints = ["/", "/api/health", "/api/rooms/AAAAAAAAAAAAAAAAAAAAAA77"]
    hdrs_ok = True
    for e in endpoints:
        r = http.get(e)
        if not (nosniff_ok(r.headers)
                and all_values(r.headers, "x-frame-options", "DENY")
                and all_values(r.headers, "referrer-policy", "no-referrer")):
            hdrs_ok = False
    check("security headers on every endpoint (nosniff/DENY/no-referrer)", hdrs_ok)

    r = http.get("/api/health", headers={"Origin": "https://evil.example"})
    check("CORS locked: no allow-origin for foreign origin",
          "access-control-allow-origin" not in r.headers)

    op = login(http, ADMIN)
    room = create_room(http, op)
    t = tok()
    join(http, room["room_id"], "hygiene", t)
    marker_token = t
    marker_room = room["room_id"]
    upload(http, room["room_id"], t, "secretname-marker.txt", b"x")
    http.post(f"/api/rooms/{room['room_id']}/items/text", json={"content": "clip"},
              headers={"X-Member-Token": t})

    malformed = http.post(f"/api/rooms/{room['room_id']}/items/text", content=b"{not json",
                          headers={"X-Member-Token": t, "Content-Type": "application/json"})
    check("malformed JSON → 422 (never 500)", malformed.status_code == 422)

    logs = subprocess.run(["docker", "logs", "cliproom-api-1", "--since", "10m"],
                          capture_output=True, text=True).stdout
    check("raw member token absent from api logs", marker_token not in logs)
    check("room ID absent from api logs", marker_room not in logs)
    check("original filename absent from api logs", "secretname-marker" not in logs)

    summary()


def summary() -> None:
    passed = sum(1 for ok, _ in results if ok)
    print(f"\nAUDIT: {passed}/{len(results)} checks passed")
    for ok, name in results:
        if not ok:
            print("  FAILED:", name)
    sys.exit(0 if passed == len(results) else 1)


PHASES = {
    "auth": phase_auth,
    "rooms": phase_rooms,
    "concurrency": phase_concurrency,
    "limit_login": phase_limit_login,
    "limit_upload": phase_limit_upload,
    "limit_ws": phase_limit_ws,
    "hygiene": phase_hygiene,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PHASES:
        print(__doc__)
        sys.exit(2)
    PHASES[sys.argv[1]]()
