# ClipRoom

Self-hosted, ephemeral, **live shared scratch rooms** behind unguessable links.
Share text snippets and files with strangers in real time — no accounts, no
apps: one link is all it takes.

> **Status: specification phase.** This repository currently contains the
> authoritative specification ([SPECS.md](SPECS.md)) written before any
> implementation code, per the AI Dev Tools Zoomcamp final-project workflow.
> Implementation proceeds against the acceptance criteria in SPECS.md §10.

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

Not yet implemented — see [SPECS.md](SPECS.md). Target behavior once built:

```bash
docker compose up --build   # full stack, one command
make test                   # backend + frontend + integration tests
```

## License

TBD by the author.
