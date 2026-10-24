# ClipRoom

Self-hosted, ephemeral, **live shared scratch rooms** behind unguessable links.
Share text snippets and files with strangers in real time — no accounts, no
apps: one link is all it takes.

> **Status: implemented against SPECS.md.** The specification
> ([SPECS.md](SPECS.md)) was written before any code; every requirement traces
> to tracker issues #1–#19 (one per acceptance criterion, §10) and commits
> reference them.

## The problem

Sharing a few text snippets and files with strangers — workshop attendees, game
teammates, a client on a support call — currently forces a bad choice:

- **Account-and-app tools** (Google Docs, Slack, Discord): everyone must create
  accounts and install apps; overkill for a 10-minute exchange with strangers.
- **Single-paste tools** (PrivateBin): one author, passive viewers, manual
  refresh; the paste cannot keep receiving new content from everyone during
  the session.

**ClipRoom** fixes this: the operator creates a room, shares one unguessable
URL (`https://<host>/r/<room-id>`), and everyone holding the full link shares a
live canvas of **text clips and file attachments** — new items appear on every
screen within ~1 second. Rooms expire automatically and are deleted together
with their files.

## How it works (expected behavior)

- The full room link is the only member credential. No link, no access — and
  unknown links return a generic 404, so rooms cannot even be probed for.
- On first entry, each visitor picks a display name (1–20 chars); the name and
  a private member token stay in their browser.
- Every link-holder can add text clips and upload files (size-capped,
  type-filtered). Everyone sees all changes live via WebSocket, plus a
  "in this room now" presence list.
- **Delete-own-only:** a member can delete only items they added — enforced
  server-side via hashed member tokens.
- The operator administers the instance through an **admin account**
  (unlimited rooms, dashboard, force-terminate) and an optional **guest/demo
  account** (exactly one active room, deletable by itself only) — both
  configured via environment variables, never stored in the app.
- Rooms have a TTL (1h / 24h / 7d, extended on activity). A background sweeper
  deletes expired rooms, their files, and orphaned uploads.

## How ClipRoom differs from existing open-source tools

All facts verified October 2026 against each project's README/changelog.

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
- **Mixed content on one canvas**: text clips and file attachments side by side.
- **Per-room capability URLs hardened for public exposure** (private
  local-content-share instances have no access control at all).
- **Member identity without accounts**: display names, per-member colors, live
  presence, and server-enforced delete-own-only.
- **Operator roles without member accounts** (admin + limited guest, from env).
- **Automatic expiry with orphan-file cleanup** as a first-class background job.

## Documentation

- [SPECS.md](SPECS.md) — authoritative specification: problem, competitor
  analysis, functional/security requirements (FR/SR), API + WebSocket contract,
  data model, testing, CI/CD, observability, alerting, on-call agent, and the
  verifiable acceptance criteria (§10).
- `docs/teams.md`, `docs/process.md`, `docs/api.md` — created during the build
  phase (see SPECS.md §5 repository layout).

## Setup & running

One command starts the entire stack (frontend, api, SQLite + file volumes,
Mailpit, OpenTelemetry collector, Prometheus, Alertmanager, Tempo, Loki,
Grafana):

```bash
docker compose up --build
```

Then:

| What | URL |
|---|---|
| App (operator login) | http://localhost:8080/admin |
| Room links | http://localhost:8080/r/&lt;room-id&gt; (created by an operator) |
| Grafana (dashboards, traces, logs) | http://localhost:3300 (anonymous admin) |
| Prometheus / Alertmanager | http://localhost:9090 / http://localhost:9093 |
| Mailpit (alert escalation email) | http://localhost:8025 |

**Local-dev bootstrap credentials** (active only because compose sets
`CLIPROOM_DEV=1`; production must set real env vars — see
`backend/app/config.py`):

- admin: `admin` / `cliproom-dev-admin`
- guest/demo: `guest` / `cliproom-dev-guest`

Generate production password hashes with `bash scripts/hash_password.sh '<password>'`
(argon2id) and set `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `SESSION_SECRET`,
`AGENT_TOKEN`, `BASE_URL` (plus optional `GUEST_*` and the alertmanager bearer
token in `ops/alertmanager/alertmanager.yml`).

### Tests — one command

```bash
make test          # or: bash scripts/test.sh  (no make on Windows)
```

Runs the backend unit + integration suites (pytest) and the frontend suites
(Vitest). CI (`.github/workflows/ci.yml`) additionally lints and builds the
full compose stack on every PR.

### Manual acceptance demo (AC9/AC10)

1. Sign in at `/admin` (admin creds above) → create a room → copy the share URL.
2. Open the URL in **two browser windows**; pick different names in each.
3. In window A: add a text clip and upload a file. It appears in window B
   within ~1 s; both presence chips show both members.
4. In window B: try the Delete button on A's item (absent — own items only);
   in A, delete it — it disappears from both.
5. Reload window B — the join screen is skipped (identity in localStorage),
   full state returns, colors are stable.

### Deployment & rollback (AC15/AC16)

- CI: lint + tests + compose build on every PR (`.github/workflows/ci.yml`).
- CD: `deploy-dev.yml` auto-deploys on merge to main over SSH
  (`docker compose up --build -d`) and smoke-checks `/api/health`;
  `deploy-prod.yml` is a manual `workflow_dispatch` gated by the
  `production` environment's required reviewers; `rollback.yml` redeploys the
  previous commit/image tag and smoke-checks again.
- Host secrets used by the workflows: `SSH_HOST`, `SSH_USER`, `SSH_KEY`,
  `DEPLOY_DIR`, `DEV_PUBLIC_HOST`, `PROD_PUBLIC_HOST` (repo → Settings →
  Secrets). The rollback drill (checkout previous commit → compose up →
  health check → forward again) was executed and verified once against the
  local compose stack; see the tracker issue #15 for the transcript.

## License

TBD by the author.
