"""Live multi-member smoke test against the running compose stack.

Exercises the REAL path: nginx frontend proxy (REST + WebSocket upgrade) →
api. Two concurrent members in one room:
  join → both WS connected → A adds text → B uploads a file →
  A deletes own item → presence shows both → timings recorded.

Usage: python scripts/live_smoke.py [base_url]
"""
from __future__ import annotations

import asyncio
import secrets
import sys
import time

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
WS_BASE = BASE.replace("http://", "ws://")


def token() -> str:
    return secrets.token_hex(32)


async def recv_until(ws, want_type: str, timeout: float = 2.0) -> tuple[dict, float]:
    """Receive events until one matches; returns (event, elapsed_since_call)."""
    started = time.perf_counter()
    while True:
        remaining = timeout - (time.perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError(f"no '{want_type}' event within {timeout}s")
        event = await asyncio.wait_for(ws.recv(), timeout=remaining)
        data = __import__("json").loads(event)
        if data.get("type") == want_type:
            return data, time.perf_counter() - started


async def main() -> None:
    ok = []

    async with httpx.AsyncClient(base_url=BASE, timeout=10) as http:
        # operator creates a room (route the Secure session cookie manually —
        # cookie jars won't replay it over plain http)
        r = await http.post(
            "/api/admin/login",
            json={"username": "admin", "password": "cliproom-dev-admin"},
            headers={"X-Requested-With": "fetch"},
        )
        assert r.status_code == 200, r.text
        sid = r.headers["set-cookie"].split("cliproom_session=")[1].split(";")[0]
        op_headers = {"X-Requested-With": "fetch", "Cookie": f"cliproom_session={sid}"}
        r = await http.post("/api/rooms", json={"ttl": "1h"}, headers=op_headers)
        assert r.status_code == 200, r.text
        room_id = r.json()["room_id"]
        print(f"room created: {room_id}  share URL: {BASE}/r/{room_id}")

        tok_a, tok_b = token(), token()
        ra = await http.post(
            f"/api/rooms/{room_id}/join",
            json={"name": "alice"},
            headers={"X-Member-Token": tok_a},
        )
        rb = await http.post(
            f"/api/rooms/{room_id}/join",
            json={"name": "bob"},
            headers={"X-Member-Token": tok_b},
        )
        assert ra.json()["name"] == "alice" and rb.json()["name"] == "bob"
        ok.append("two members joined with distinct identities/colors")

        tickets = {}
        for name, tok in (("alice", tok_a), ("bob", tok_b)):
            t = (
                await http.post(
                    f"/api/rooms/{room_id}/ws-ticket", headers={"X-Member-Token": tok}
                )
            ).json()["ticket"]
            tickets[name] = t

        async with websockets.connect(
            f"{WS_BASE}/api/rooms/{room_id}/ws?ticket={tickets['alice']}"
        ) as ws_a, websockets.connect(
            f"{WS_BASE}/api/rooms/{room_id}/ws?ticket={tickets['bob']}"
        ) as ws_b:
            state_a = await asyncio.wait_for(ws_a.recv(), 3)
            state_b = await asyncio.wait_for(ws_b.recv(), 3)
            import json

            assert json.loads(state_a)["type"] == "state"
            sb = json.loads(state_b)
            assert sb["type"] == "state"
            names = {m["name"] for m in sb["members"]}
            assert names == {"alice", "bob"}, names
            ok.append("both WebSocket connections live via nginx proxy; presence shows both")

            # A adds a text clip → must reach BOTH sockets fast
            r = await http.post(
                f"/api/rooms/{room_id}/items/text",
                json={"content": "hello from alice"},
                headers={"X-Member-Token": tok_a},
            )
            item = r.json()
            ev_a, t_a = await recv_until(ws_a, "item_added")
            ev_b, t_b = await recv_until(ws_b, "item_added")
            assert ev_a["item"]["item_id"] == item["item_id"] == ev_b["item"]["item_id"]
            assert ev_a["item"]["author"]["name"] == "alice"
            ok.append(f"alice's text clip reached alice in {t_a*1000:.0f} ms and bob in {t_b*1000:.0f} ms")

            # B uploads a file → must reach BOTH sockets
            files = {"file": ("notes.csv", b"a,b\n1,2\n", "text/csv")}
            r = await http.post(
                f"/api/rooms/{room_id}/items/file",
                files=files,
                headers={"X-Member-Token": tok_b},
            )
            fitem = r.json()
            assert fitem["kind"] == "file" and fitem["file"]["name"] == "notes.csv"
            ev_a, t_a = await recv_until(ws_a, "item_added")
            ev_b, t_b = await recv_until(ws_b, "item_added")
            assert ev_a["item"]["item_id"] == fitem["item_id"] == ev_b["item"]["item_id"]
            assert ev_a["item"]["author"]["name"] == "bob"
            ok.append(f"bob's file upload reached alice in {t_a*1000:.0f} ms and bob in {t_b*1000:.0f} ms")

            # B cannot delete A's clip; A can
            r = await http.delete(
                f"/api/rooms/{room_id}/items/{item['item_id']}",
                headers={"X-Member-Token": tok_b},
            )
            assert r.status_code == 403, r.text
            r = await http.delete(
                f"/api/rooms/{room_id}/items/{item['item_id']}",
                headers={"X-Member-Token": tok_a},
            )
            assert r.status_code == 200
            ev_a, _ = await recv_until(ws_a, "item_deleted")
            ev_b, _ = await recv_until(ws_b, "item_deleted")
            assert ev_a["item_id"] == item["item_id"] == ev_b["item_id"]
            ok.append("delete-own-only enforced live; deletion broadcast to both")

            # full state for a late REST fetch reflects both items' aftermath
            state = (await http.get(f"/api/rooms/{room_id}/items")).json()
            assert [i["item_id"] for i in state["items"]] == [fitem["item_id"]]
            ok.append("REST full state consistent (only bob's file remains)")

    print("\nLIVE MULTI-MEMBER TEST — PASS")
    for line in ok:
        print("  ✓", line)


if __name__ == "__main__":
    asyncio.run(main())
