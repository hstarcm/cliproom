# API + WebSocket contract

From SPECS.md §6. This is the implementer-facing expansion; SPECS.md remains
authoritative on conflict.

## Conventions

- All REST under `/api`, JSON bodies unless noted.
- Member mutations carry `X-Member-Token: <64-hex>` (client-generated 32 random
  bytes, hex; server stores SHA-256 only).
- Operator (admin/guest) routes use the session cookie set at login **and**
  the header `X-Requested-With: fetch` on mutating calls (CSRF, SR-7).
- Error semantics (member-facing): unknown/expired/deleted room → **404 with a
  generic body, never 403**; wrong/missing member token on a known room →
  **403**; file too large → **413**; disallowed type → **415**; validation →
  **422**; rate limited → **429**; unauthenticated operator action → **401**;
  guest touching admin/other-room resources → **403**; guest second active
  room → **409**.

## REST endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/admin/login` | none | `{username, password}` → session cookie + `{role: "admin"\|"guest"}`; generic errors; rate-limited 5/15min/IP |
| POST | `/api/admin/logout` | session | destroy session server-side |
| GET | `/api/admin/rooms` | admin only | active rooms `[{room_uuid, room_id, share_url, item_count, disk_usage, expires_at, created_by}]` |
| DELETE | `/api/admin/rooms/{room_uuid}` | admin only | force-terminate any room + files (members then get 404) |
| POST | `/api/rooms` | admin or guest session | `{ttl: "1h"\|"24h"\|"7d"\|"<n>m\|h\|d"\|"forever", max_file_mb?: int}` → `{room_id, share_url, expires_at}` (expires_at null for forever); guest with active room → 409; custom TTL bounded 1m–365d; max_file_mb 1–global cap |
| DELETE | `/api/rooms/{room_uuid}` | admin (any) or guest (own) | terminate room + files |
| GET | `/api/rooms/{room_id}` | member (link) | `{expires_at, item_count, max_file_mb}` — max_file_mb is the room's effective upload cap |
| POST | `/api/rooms/{room_id}/join` | member token | `{name}` → `{member_id, name, color}` |
| GET | `/api/rooms/{room_id}/items` | member (link) | full state `{items, members_present}` |
| POST | `/api/rooms/{room_id}/items/text` | member token | `{content}` → item |
| POST | `/api/rooms/{room_id}/items/file` | member token | multipart file → item; size capped by the room's `max_file_mb` when set, else the global `MAX_FILE_MB` |
| DELETE | `/api/rooms/{room_id}/items/{item_id}` | creator's token | delete-own-only (200 / 403) |
| POST | `/api/rooms/{room_id}/ws-ticket` | member token | one-time ticket, 60 s TTL |
| POST | `/api/agent/on-alert` | `AGENT_TOKEN` | Alertmanager webhook target (SPECS §7) |
| GET | `/api/health` | none | liveness + DB check |

Room IDs: base62, ≥22 chars (≈128 bits). Share URL: `BASE_URL + /r/<room_id>`.

## WebSocket

`GET /api/rooms/{room_id}/ws?ticket=<one-time ticket>` — the ticket comes from
`POST .../ws-ticket` so member tokens never appear in access logs (SR-7).
Tickets are single-use and expire in 60 s.

- Client → server: `{"type":"heartbeat"}` every 30 s. Idle >5 min ⇒ member
  dropped from presence (not from the room).
- Server → client (JSON; `room_uuid` surrogate only — never the room id):
  - `{"type":"state","items":[...],"members":[...]}` — on (re)connect, full current state
  - `{"type":"item_added","item":{...}}`
  - `{"type":"item_deleted","item_id":"..."}`
  - `{"type":"member_joined","member":{"member_id","name","color"}}`
  - `{"type":"member_left","member_id":"..."}`
  - `{"type":"presence","members":[...]}`
- Item shape: `{item_id, kind: "text"|"file", content?, file?: {file_id, name,
  size, mime}, author: {member_id, name, color}, created_at}`.
- Client auto-reconnects with exponential backoff, 1 s → 30 s cap; on reconnect
  it receives full state (missed events cannot accumulate).

## Data model (SQLite, WAL)

- `rooms(room_id PK, room_uuid, created_by TEXT CHECK(created_by IN ('admin','guest')), created_at, ttl_seconds NULL, expires_at NULL, max_file_mb NULL, last_activity_at)` — NULL `ttl_seconds`/`expires_at` = forever room (FR-19); NULL `max_file_mb` = global cap (FR-13a)
- `members(member_id PK, room_id FK, name, color, token_hash UNIQUE, joined_at)`
- `items(item_id PK, room_id FK, author_member_id FK, kind, content, file_name, file_path, file_size, mime, created_at)`
- `sweeper_runs(id PK, started_at, finished_at, rooms_deleted, files_deleted, orphans_deleted, status)`
- `agent_actions(id PK, alert_name, started_at, diagnosis, actions, outcome)`

## Rate limits (SR-3, per-IP, configurable)

login ≤5/15 min · room creation ≤5/h · uploads ≤30/h · item deletes ≤60/h ·
WS connections ≤10/IP · exceeding → 429.
