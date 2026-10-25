# SPECS.md — ClipRoom

Self-hosted, ephemeral, live shared scratch rooms behind unguessable links.
One container stack; room members never create accounts — the full room URL is
their only credential. One admin and one optional guest/demo operator account
(from environment variables) manage room creation.

> **Document status:** authoritative specification, written before any code
> (course requirement: "specify the problem and its acceptance criteria before
> writing the code"). Section 3 (FR/SR) is the canonical contract; section 10
> is the verifiable acceptance checklist. Implementers — human or AI — should
> trace every commit and test to a requirement ID and self-report against
> section 10 when done.

---

## 1. Problem statement

Sharing a handful of text snippets and files with strangers — workshop attendees,
game teammates, a client on a support call — currently forces a bad choice:

- **Account-and-app tools** (Google Docs, Slack, Discord): everyone must create
  accounts and install apps; overkill for a 10-minute exchange with strangers.
- **Single-paste tools** (PrivateBin): one author, passive viewers, manual
  refresh; the paste cannot keep receiving new content from everyone during the
  session.

**ClipRoom** is a self-hosted web application: the operator creates a room,
shares one unguessable URL (`https://<host>/r/<room-id>`), and every person
holding the full link joins a **live shared canvas of text clips and file
attachments**. New items appear on every participant's screen within ~1 second.
Rooms expire automatically and are deleted together with their files.

### Expected behavior in one sentence
Every link-holder — after picking a display name — can add text clips and upload
files that everyone sees live; each member can delete **only their own** items;
the operator (admin, or a guest account limited to one room) creates and removes
rooms; rooms and files vanish when their TTL lapses.

---

## 2. Differences from existing open-source tools (README-ready)

All facts below were verified in October 2026 against each project's
README/changelog at the time of writing. This section doubles as the project
README's positioning table: it demonstrates ClipRoom is a deliberate composition
of proven ideas, not an accidental duplicate.

| # | App | Text+files | Live sync | Multi-party room | Capability link | Own-item deletion | Names/presence | Ephemeral |
|---|-----|-----------|-----------|------------------|-----------------|-------------------|----------------|-----------|
| 1 | PrivateBin v2.1.0 | one paste (+async comments) | ❌ manual refresh | ❌ one-way (author → viewers) | ✅ key in URL fragment | n/a | ❌ | ✅ TTL / burn-after-read |
| 2 | local-content-share | ✅ both | ⚠️ SSE broadcast | ⚠️ one global shared space, no per-room isolation | ❌ no authentication at all (LAN/homelab-only per README) | ❌ | ❌ | ✅ per-item TTL |
| 3 | tfranzel/scratchpad | ✅ both | ✅ WebSocket | ❌ exactly two parties (sender/recipient) | ⚠️ ECDH key agreement, not per-room URLs | n/a | ❌ | ❌ not documented |
| 4 | Rustpad (also Etherpad, HedgeDoc) | ❌ text/code only | ✅ WebSocket (OT/CRDT co-editing) | ✅ per-document links | ⚠️ URL knowledge = access | n/a (shared document model) | ⚠️ cursors/labels only | ❌ persistent pads |
| 5 | Wormhole (also Send forks, Palmr, Erugo) | ❌ files only | ❌ | ❌ one sender → N recipients, one-way | ✅ link (optionally password) | n/a | ❌ | ✅ expiring transfers |

**What ClipRoom adds — the combination nobody ships:**

- An **N-party live room** (not one author, not two parties): every link-holder
  contributes throughout the session over WebSocket.
- **Mixed content on one canvas**: text clips and file attachments side by side
  (PrivateBin/Rustpad/Wormhole each cover only one content type, or are one-way).
- **Per-room capability URLs hardened for public exposure** (local-content-share
  has no access control at all and is LAN-only by design).
- **Member identity without accounts**: required display name on join, per-member
  color, live presence list, and **delete-own-only enforcement** via hashed
  member tokens — none of the five offer scoped deletion or presence.
- **Operator roles without member accounts**: an admin account (unlimited rooms,
  dashboard, force-terminate) and a limited guest/demo account (exactly one
  active room, deletable by itself only) — both from environment variables.
- **Automatic expiry with orphan-file cleanup** as a first-class background job.

---

## 3. Functional requirements (authoritative)

Use the identifiers below as the canonical requirement IDs.

### Roles & access model

There are exactly two operator roles and one anonymous member role:

| Role | How it exists | Can do |
|---|---|---|
| **admin** | env vars `ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH` | create unlimited rooms; view all active rooms + stats; force-terminate any room; delete any room |
| **guest** (demo) | env vars `GUEST_USERNAME` + `GUEST_PASSWORD_HASH` | create **at most one** active room; delete **only that room**; nothing else |
| **member** | holding the full room URL | view, add text clips, upload files, delete **own** items |

- **FR-1 Room creation (authenticated).** `POST /api/rooms` requires an
  authenticated admin or guest session and returns
  `{room_id, share_url, expires_at}`. `room_id` is a random **base62 string of
  ≥22 characters** (≈128 bits of entropy; shorter "randomised strings" are
  brute-forceable and are a security bug, not a style choice). Unauthenticated
  creation → `401`.
- **FR-2 Capability access.** The full room URL is the only member credential.
  A request to an unknown/expired/deleted room returns **HTTP 404 with a generic
  body — never 403** — so attackers cannot distinguish "exists, forbidden" from
  "missing". (Exception: authenticated admin/gatekeeper routes may 403; member
  and anonymous routes must 404.)
- **FR-3 Accounts.** No accounts for room members — ever. There is exactly one
  admin account and optionally one guest account, both from environment
  variables; password hashes use **argon2id or bcrypt**; plaintext passwords
  never appear in compose files or logs.
- **FR-4 Admin login/session.** `POST /api/admin/login` `{username, password}`
  verifies credentials in constant time and sets an **HttpOnly, Secure,
  SameSite=Lax session cookie** (12 h expiry, invalidated server-side on
  logout). Failed logins return a generic error (no username enumeration) and
  are rate-limited to **5 per 15 min per IP** → `429`. The login response and
  session carry the resolved role (`admin` or `guest`).
- **FR-5 Admin dashboard.** Admin-only page: list of active rooms (internal
  `room_uuid` surrogate, item count, disk usage, `expires_at`) with a
  **force-terminate** action (`DELETE /api/admin/rooms/{room_uuid}`) that
  deletes the room, its files, and immediately 404s it for members. Guest
  sessions get **403** on all `/api/admin/*` routes.
- **FR-6 Agent access.** The on-call responder agent authenticates to internal
  admin endpoints with a separate `AGENT_TOKEN` env secret — it never uses the
  admin session.
- **FR-7 Guest constraints.** A guest session may have **at most one active
  room**: creating a second → `409 Conflict` with a clear message ("delete your
  current room first"). `DELETE /api/rooms/{room_uuid}` deletes the guest's own
  room (files included; members immediately get 404); afterwards the guest can
  create a new room. A guest cannot list, see, or terminate any other room.

### Join & member identity

- **FR-8 Join screen.** A visitor opening a room URL without a stored identity
  sees a join screen requiring a **display name of 1–20 characters** (trimmed;
  empty or >20 rejected with a clear error).
- **FR-9 Member token.** On join, the client generates a **member token**
  (32 random bytes, hex) via `crypto.getRandomValues`, stores it in
  `localStorage` keyed by `room_id` together with the name, and sends it with
  every mutating request (header `X-Member-Token`). The server stores only a
  **SHA-256 hash** of the token, never the token itself.
- **FR-10 Returning member.** A revisit with stored identity skips the join
  screen and re-registers presence automatically. Names are NOT
  uniqueness-enforced; each member is assigned a **color** (deterministic from
  its member id, palette of ≥8 accessible colors) so same-named members remain
  distinguishable.
- **FR-11 Identity loss.** Clearing `localStorage` forfeits name and delete
  rights for previously added items. This is documented, intended behavior.

### Content

- **FR-12 Text clips.** Any member can add a text clip: 1–10,000 characters
  (enforced server-side). Clips are ordered newest-first on the canvas.
- **FR-13 File uploads.** Any member can upload files with **max size 10 MB
  (server-enforced, configurable `MAX_FILE_MB`)** and an **allowlist** of
  extensions (deny-by-default; configurable `ALLOWED_EXTENSIONS`). Default:
  images (png/jpg/jpeg/gif/webp), pdf, text (txt/md/csv), archives
  (zip/7z/rar), code/config (py/ipynb/yaml/yml/json/toml/ini/xml/sql/
  js/mjs/cjs/ts/tsx/jsx/css/scss/less/vue/svelte/java/c/h/hpp/cc/cpp/cs/
  go/rs/rb/kt/swift/sh/bash), MS Office (doc/docx/xls/xlsx/ppt/pptx).
  Deliberately excluded: executables & server code (exe/php/jsp/…),
  browser-renderable types (html/svg — SR-5), and macro-enabled Office
  (docm/xlsm/pptm). Original filenames are preserved for download; content
  is stored on disk under `DATA_DIR/<room_id>/<file_id>`; never executed or
  served inline (`Content-Disposition: attachment`,
  `X-Content-Type-Options: nosniff`).
- **FR-13a Per-room upload cap.** The creating operator may set an optional
  `max_file_mb` for a room at creation (integer, 1 – global `MAX_FILE_MB`;
  absent → global cap). Uploads to that room are capped by the room value;
  violations → `413` naming the effective cap.
- **FR-14 Authorship display.** Every item shows "added by \<name\>" in the
  author's color, with a relative and an absolute timestamp (e.g. "2 min ago
  · 25 Oct 2026, 14:02"); the room header and presence chip mark the
  member's own name.
- **FR-15 Delete-own-only (items).** `DELETE /api/rooms/{id}/items/{item_id}`
  must carry the creator's member token. Server compares SHA-256 hash: match →
  item (and file, if any) deleted; mismatch or missing header → **HTTP 403**
  and NO broadcast. (403 is correct here: the requester already knows the room
  exists.)

### Live behavior

- **FR-16 WebSocket sync.** One WebSocket endpoint per room. Adds, deletes,
  joins, and leaves are broadcast to all connected members within **~1 second**
  of commit.
- **FR-17 Reconnect safety.** On (re)connect the client receives the full
  current room state, so missed events cannot accumulate. Client
  auto-reconnects with exponential backoff (1 s → 30 s cap).
- **FR-18 Presence.** A live "in this room now" list (name + color) maintained
  by WS join/leave events; a member idle >5 min without heartbeat is dropped
  from presence (but NOT from the room).

### Expiry & cleanup

- **FR-19 TTL.** Room TTL chosen at creation: the presets `1h` / `24h` /
  `7d`, any custom duration `<n>m|h|d` (minutes/hours/days; 1 minute – 365
  days), or `forever` (no automatic expiry — ends only by manual deletion).
  Activity (add/upload/delete) extends `expires_at = now + ttl` (forever
  rooms have no expiry to extend). Pure viewing does NOT extend.
- **FR-20 Sweeper.** A background job runs **hourly** (configurable
  `SWEEPER_INTERVAL_MIN`): deletes expired rooms, their disk directories, and
  any **orphaned files** on disk with no DB row (e.g. after a crash
  mid-upload). Every run records `{started_at, finished_at, rooms_deleted,
  files_deleted, orphans_deleted, status}` in a `sweeper_runs` table.

---

## 4. Security requirements (non-negotiable)

- **SR-1** Room IDs ≥128-bit entropy (FR-1).
- **SR-2** Member tokens stored **hashed only** (FR-9); raw tokens never
  persisted or logged. Password hashes never logged.
- **SR-3** Rate limits (configurable, per-IP): login ≤5/15 min (FR-4), room
  creation ≤5/h, uploads ≤30/h, item deletes ≤60/h, WS connections ≤10/IP.
  Exceeding → `429`.
- **SR-4** Room IDs, member tokens, member names, original filenames, and
  passwords are **never written to logs, traces, or metrics** (names are
  user-chosen = potential personal data). Telemetry uses an internal
  `room_uuid` surrogate where correlation is needed.
- **SR-5** All uploads served as attachments (FR-13); no HTML/SVG inline
  rendering; SVG excluded from the allowlist by default. Served Content-Type
  is the canonical MIME of the allowlisted extension — never the
  client-declared type — and control characters are stripped from stored
  filenames before they can reach storage or headers.
- **SR-6** CORS locked to the frontend origin; security headers:
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (a Referer
  leak could expose room URLs), `X-Frame-Options: DENY`.
- **SR-7** Session cookies: HttpOnly, Secure, SameSite=Lax, 12 h expiry,
  server-side invalidation on logout. CSRF protection for mutating
  authenticated calls: SameSite=Lax plus a required custom header
  (`X-Requested-With: fetch`). WS auth uses **one-time short-lived tickets**
  (FR-17 §5) so member tokens never appear in access logs or query strings.

---

## 5. Architecture & tech stack

```
┌ docker compose ─────────────────────────────────────────────┐
│  frontend (React/Vite, nginx)  ──HTTP/WS──▶  api            │
│                                              FastAPI        │
│  db: SQLite file volume ◀── SQLAlchemy ──────┤  + APScheduler│
│  DATA_DIR volume (uploaded files) ◀──────────┘  (sweeper)    │
│                                                             │
│  mailpit (SMTP sink, dev)      otel-collector               │
│  grafana ◀ tempo(traces) + prometheus(metrics) + loki(logs) │
└─────────────────────────────────────────────────────────────┘
```

- **Backend:** Python 3.12, FastAPI, uvicorn, SQLAlchemy 2.x, APScheduler
  (in-process sweeper), native FastAPI WebSocket support.
- **Database:** SQLite (WAL mode) in a Docker volume; sufficient for the
  workload; SQLAlchemy keeps Postgres swappable.
- **Frontend:** React 18 + Vite + TypeScript; fetch + native WebSocket (no
  state library needed); Vitest for frontend tests.
- **File storage:** local disk volume (not DB blobs).
- **Email (dev):** Mailpit container; SMTP via env vars.

### Environment variables (configuration contract)

| Variable | Purpose | Default |
|---|---|---|
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` | admin operator account | required |
| `GUEST_USERNAME`, `GUEST_PASSWORD_HASH` | guest/demo operator account | optional (role disabled if unset) |
| `SESSION_SECRET` | session cookie signing | required |
| `AGENT_TOKEN` | on-call agent → internal endpoints | required |
| `BASE_URL` | used to build `share_url` (e.g. `https://abc.dedyn.io`) | required |
| `MAX_FILE_MB` | global upload cap (per-room override: FR-13a) | `10` |
| `ALLOWED_EXTENSIONS` | upload allowlist | see FR-13 |
| `DATA_DIR`, `DB_PATH` | storage locations | `/data/files`, `/data/cliproom.db` |
| `SWEEPER_INTERVAL_MIN` | sweeper period | `60` |
| `RATE_LIMIT_*` | limits per SR-3 | see SR-3 |
| `SMTP_HOST/PORT/USER/PASS/FROM` | alert email (Mailpit in dev) | Mailpit defaults |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | telemetry pipeline | `http://otel-collector:4318` |

### Repository layout

```
cliproom/
├── SPECS.md                  # this file
├── README.md                 # problem, positioning table (§2), setup, demo
├── AGENTS.md                 # agent instructions; points to docs/
├── docs/
│   ├── teams.md              # agent team spec (§8)
│   ├── process.md            # workflow: spec → issues → implement → review
│   └── api.md                # API + WS contract (from §6)
├── backend/
│   ├── app/                  # FastAPI app (routers, models, ws, sweeper, agent)
│   ├── tests/                # pytest unit + integration
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/                  # React app (pages/, components/, lib/)
│   ├── tests/                # Vitest
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml        # single command: full stack
├── Makefile                  # make test | make up | make down
└── .github/workflows/        # ci.yml, deploy-dev.yml, deploy-prod.yml, rollback.yml
```

---

## 6. API contract (full details in docs/api.md)

### REST (JSON; `X-Member-Token` on member mutations; session cookie for operator routes; `X-Requested-With: fetch` on mutating authenticated calls)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/admin/login` | none | `{username, password}` → session cookie + `{role: "admin"\|"guest"}`; rate-limited |
| POST | `/api/admin/logout` | session | destroy session |
| GET | `/api/admin/rooms` | admin only | active rooms: `[{room_uuid, room_id, share_url, item_count, disk_usage, expires_at, created_by}]` (room_id + share_url exposed to the authenticated admin for dashboard room links/QR) |
| DELETE | `/api/admin/rooms/{room_uuid}` | admin only | force-terminate any room + files |
| POST | `/api/rooms` | admin or guest session | create room `{ttl: "1h"\|"24h"\|"7d"\|"<n>m|h|d"\|"forever", max_file_mb?: int}` → `{room_id, share_url, expires_at}`; guest with an active room → `409` |
| DELETE | `/api/rooms/{room_uuid or room_id}` | admin (any) or guest (own) | terminate room + files; members immediately get 404 |
| GET | `/api/rooms/{room_id}` | member (link) | room metadata `{expires_at, item_count, max_file_mb}` (max_file_mb = effective per-room/global cap, FR-13a) |
| POST | `/api/rooms/{room_id}/join` | member token | `{name}` → `{member_id, name, color}` |
| GET | `/api/rooms/{room_id}/items` | member (link) | full state `{items, members_present}` |
| POST | `/api/rooms/{room_id}/items/text` | member token | `{content}` → item |
| POST | `/api/rooms/{room_id}/items/file` | member token | multipart file → item |
| DELETE | `/api/rooms/{room_id}/items/{item_id}` | creator's token | delete-own-only |
| POST | `/api/rooms/{room_id}/ws-ticket` | member token | one-time ticket (60 s TTL) for WS auth |
| POST | `/api/agent/on-alert` | `AGENT_TOKEN` | Alertmanager webhook target (§7) |
| GET | `/api/health` | none | liveness + DB check (smoke test target) |

Member-facing error semantics: unknown room → `404` (generic body); wrong/missing
member token on a known room → `403`; file too large → `413`; disallowed type →
`415`; validation → `422`; rate limit → `429`. Constant-time hash comparisons;
no user enumeration anywhere.

### WebSocket `GET /api/rooms/{room_id}/ws?ticket=<one-time ticket>`

- Auth: one-time ticket from `POST .../ws-ticket` (so tokens stay out of access
  logs; SR-7).
- Client→server: `{"type":"heartbeat"}` every 30 s.
- Server→client events (JSON; `room_uuid` surrogate only — never the room id):
  - `{"type":"state","items":[...],"members":[...]}` (on connect)
  - `{"type":"item_added","item":{...}}`
  - `{"type":"item_deleted","item_id":"..."}`
  - `{"type":"member_joined","member":{"member_id","name","color"}}`
  - `{"type":"member_left","member_id":"..."}`
  - `{"type":"presence","members":[...]}` (after any membership change)
- Item shape: `{item_id, kind: "text"|"file", content?, file?: {file_id, name,
  size, mime}, author: {member_id, name, color}, created_at}`.

### Data model (SQLite)

- `rooms(room_id PK, room_uuid, created_by TEXT CHECK(created_by IN
  ('admin','guest')), created_at, ttl_seconds NULL, expires_at NULL,
  max_file_mb NULL, last_activity_at)` — NULL ttl/expires = forever (FR-19);
  NULL max_file_mb = global cap (FR-13a)
- `members(member_id PK, room_id FK, name, color, token_hash UNIQUE, joined_at)`
- `items(item_id PK, room_id FK, author_member_id FK, kind, content, file_name,
  file_path, file_size, mime, created_at)`
- `sweeper_runs(id PK, started_at, finished_at, rooms_deleted, files_deleted,
  orphans_deleted, status)`
- `agent_actions(id PK, alert_name, started_at, diagnosis, actions, outcome)`

---

## 7. Observability, alerting, on-call agent

**Key user journey to instrument:** *upload → validate → store → broadcast*
(the highest-risk path for real user impact).

- **Traces:** OpenTelemetry SDK → OTLP → **Tempo**, viewed in **Grafana**.
  Spans: `http.upload`, `validate_file`, `persist_file`, `ws.broadcast`.
- **Metrics:** Prometheus: `cliproom_uploads_total{result}`,
  `cliproom_upload_duration_seconds`, `cliproom_ws_clients`,
  `cliproom_sweeper_last_success_timestamp`, `cliproom_items_total`. No labels
  containing room IDs, tokens, names, or filenames (SR-4).
- **Logs:** structured JSON → OTLP → **Loki**; every line carries `trace_id`
  correlating with the trace; room IDs/tokens/names/filenames redacted.
- All three signals viewable in **Grafana** (one UI).

**Alerts (≥1 required; implement both):**

- `ALERT UploadErrorSpike` —
  `rate(cliproom_uploads_total{result="error"}[5m]) > 0.2 *
  rate(cliproom_uploads_total[5m])` and rate > 0 → user impact: people cannot
  share files.
- `ALERT SweeperStalled` —
  `time() - cliproom_sweeper_last_success_timestamp > 7200` → user impact:
  expired rooms/files accumulate (privacy + disk).

**Alert trigger:** Prometheus **Alertmanager** fires → `POST /api/agent/on-alert`
with the alert payload.

**On-call responder agent** (course requirement: "an agent wakes up on an alert
and fixes the issue") — a small `agent` module (Python; rules required, LLM
optional):

1. Receives the Alertmanager webhook.
2. Diagnoses: queries recent correlated error logs via Loki (an LLM call may
   summarize the diagnosis; a deterministic fallback must exist).
3. Remediates:
   - `UploadErrorSpike` → verify disk space + DB writability → restart the
     upload subsystem via an internal admin endpoint → synthetic upload re-test;
     email escalation if the re-test fails.
   - `SweeperStalled` → trigger the sweeper manually, re-run orphan cleanup,
     verify `cliproom_sweeper_last_success_timestamp` increments.
4. Records every action in `agent_actions` and re-notifies if remediation failed.

---

## 8. Agent team specification (for docs/teams.md)

| Agent | Responsibility | Hands off to |
|---|---|---|
| Spec agent | maintains SPECS.md; turns requirements into tracker issues with acceptance criteria | Implementer |
| Implementer | writes backend/frontend code against issues; references issue IDs in commits | Test writer, Reviewer |
| Test writer | owns unit/integration/Vitest suites; red-green for every FR | Reviewer |
| Reviewer | reviews AI-generated diffs against SPECS.md (especially §4 security) | Implementer (fix loop) |
| DevOps agent | Dockerfiles, compose, CI/CD, observability config, deploy/rollback | Reviewer |
| On-call agent | runtime responder (§7) — a shipped artifact, not a dev-time role | — |

Process: all work tracked in GitHub Issues (public tracker); each issue carries
its acceptance criteria; PRs link issues; the tracker evidences agent usage
(issue comments/commits referencing them).

---

## 9. Testing requirements

All tests pass with **one command**: `make test`
(= `pytest backend/tests` + `vitest run frontend/tests`).

**Backend unit (pytest):**
- ID generation: length ≥22, base62 alphabet, uniqueness over 10k draws.
- Expiry math: TTL extension on activity; sweeper deletes expired, keeps
  active (forever rooms never swept); orphan-file detection.
- Room options (AC20): TTL parser (presets, `<n>m|h|d` 1m–365d, forever,
  rejects invalid); forever semantics (null expiry end-to-end, sweeper-proof,
  admin-terminable, occupies guest's slot); per-room `max_file_mb`
  (clamped to global cap, enforced with room-specific 413).
- Upload validation: size cap, allowlist, correct rejection codes (413/415).
- Item ownership: delete own → 200; other's → 403; missing token → 403;
  constant-time hash compare.
- Room access: unknown room → 404; known room + wrong member token → 403
  (never 404).
- Auth: role resolution, session flags/expiry, logout invalidation, generic
  login errors, login rate limit (clock injected).
- Guest rules: second active room → 409; own-room delete → 200; other-room
  delete → 403; recreate after delete works.
- Join validation: name bounds; color determinism.
- Rate limiter windows and 429 behavior (clock injected).
- WS broadcast: fake socket registry — events reach all sockets, none after
  delete rejection.

**Backend integration (pytest + FastAPI TestClient):**
- Full journey: admin login → create room → 2 members join → add text → upload
  file → A deletes own item → B's delete of A's item → 403 → guest login →
  create own room → second create → 409 → guest deletes own room → members
  get 404 → expired room → 404. Mailpit optional.

**Frontend (Vitest):**
- Login form + join screen validation (1–20 chars; persist to localStorage).
- Item list rendering: author color, "added by", relative + absolute time;
  own-chip "(you)" marker in presence.
- Delete button visibility: own items only.
- WS client: event application + reconnect backoff (mocked socket).

**Manual acceptance script (documented in README):** two browser windows side
by side on one room — adds/deletes/joins appear live in both.

---

## 10. Acceptance criteria checklist (verifiable)

- [ ] **AC1** Admin **and** guest sessions can each create a room returning a
      share URL with a ≥22-char base62 ID; unauthenticated create → 401; guest
      second active room → 409.
- [ ] **AC2** Valid room URL → room page; unknown/expired/deleted ID → generic
      404 (never 403, no stack info) for members and anonymous visitors.
- [ ] **AC3** Login: wrong password → generic error; 6th attempt in 15 min →
      429; successful login sets HttpOnly/Secure/SameSite=Lax cookie with role;
      logout invalidates server-side.
- [ ] **AC4** Guest can delete its own room (members then get 404, files gone,
      re-create works); guest gets 403 on other rooms and all admin routes.
- [ ] **AC5** First visit enforces 1–20 char name; name + token persist in
      localStorage; revisit skips join; returning member keeps name and color.
- [ ] **AC6** Any member adds a text clip (1–10k chars enforced); visible to
      all connected members ≤1 s.
- [ ] **AC7** Uploads ≤10 MB and allowlisted types only; violations → clear
      413/415; downloads served as attachments with safe headers.
- [ ] **AC8** Delete-own items: author → 200 + broadcast; another member's
      item → 403; no token → 403; rejected deletes never broadcast.
- [ ] **AC9** Two browser windows: add/delete/join in one appears in the other
      ≤1 s; a reconnecting client receives the correct full state.
- [ ] **AC10** Presence list updates on join/leave; idle member dropped from
      presence after 5 min without heartbeat (room membership unaffected).
- [ ] **AC11** Room past its TTL (no activity extension) is deleted by the
      sweeper with its files; orphaned files cleaned; run recorded in
      `sweeper_runs`; expired room returns 404.
- [ ] **AC12** Admin dashboard lists active rooms with stats; force-terminate
      deletes room + files immediately; guest blocked (403).
- [ ] **AC13** `docker compose up --build` starts the entire stack (frontend,
      api, db volume, files volume, mailpit, observability); app fully usable
      locally with that one command.
- [ ] **AC14** `make test` runs backend unit + integration + frontend suites;
      all pass.
- [ ] **AC15** Public URL reachable (Fly.io/Render/VPS) — or a clear demo of
      the deployment documented as fallback; rollback path (redeploy previous
      image tag) documented and tested once.
- [ ] **AC16** CI: lint + tests on every PR; CD: auto-deploy to dev on merge
      to main (with `/api/health` smoke check); manual `workflow_dispatch`
      deploy to production with reviewer approval.
- [ ] **AC17** Upload→broadcast journey visible in Grafana as metrics + traces
      + structured logs sharing a `trace_id`; telemetry contains no room IDs,
      tokens, names, filenames, or credentials.
- [ ] **AC18** At least one alert fires on real user impact (test: induce the
      failure → alert arrives via Alertmanager → email/webhook).
- [ ] **AC19** On-call agent wakes on the alert, performs diagnosis +
      remediation, records it in `agent_actions`, and the failing condition
      returns to green (verified by metric).
- [ ] **AC20** Operators can create rooms with custom TTLs (`45m`, `12h`,
      `30d`…) or `forever` (never auto-expires; sweeper skips it; manual
      deletion still works; activity extension applies only to timed rooms),
      and with an optional per-room `max_file_mb` (≤ global cap) that
      overrides the global upload cap for that room (413 on violation).

---

## 11. Out of scope (future work — do NOT build)

Read-only share links · moderation/any-member-item deletion · drawing canvas
(Excalidraw-style) · end-to-end client-side encryption · multi-file zip
download · room passwords as second factor · unique-username enforcement ·
multiple guest accounts or member accounts · mobile apps · multi-node scaling /
Postgres migration.
