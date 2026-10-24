# ClipRoom — Tracker-First Build Plan (revised per course workflow)

## Phase A — GitHub repo + public task tracker + context docs
*Course criteria: Product Specification (tracker + agent evidence), Agent Team Spec, Context Management*

1. **Verify tooling**: check `gh` CLI is installed and authenticated (if not, you run `gh auth login` and I continue).
2. **Create repo**: `git init` in `C:\AnacondaWork\ClipRoom`, add `.gitignore`, create **public** repo `cliproom` via `gh repo create`, commit `README.md` + `SPECS.md`, push `main`.
3. **Context docs** (criteria 3+4): write `AGENTS.md` (instructions, pointing to modular docs), `docs/teams.md` (agent team from SPECS.md §8), `docs/process.md` (spec → issues → implement → review workflow), `docs/api.md` (API + WS contract from §6). Commit + push.
4. **Open 19 issues** — one per AC (AC1–AC19). Each issue body: the AC text as acceptance criteria + related FR/SR requirement IDs + labels (`backend` / `frontend` / `devops` / `observability` / `testing`).
5. **Tracker evidence rule** (from here on): every commit references issue #s (`closes #N` when done); progress comments posted on issues as phases complete — this is the "agents used the tracker" evidence.

## Phase B — Scaffold & containerization (criteria: Application, Containerization)
6. Repo layout per §5: `backend/` (FastAPI app factory, pyproject, Dockerfile), `frontend/` (Vite + React 18 + TS, Dockerfile), `docker-compose.yml` (api, frontend, volumes, mailpit, otel-collector, grafana/prometheus/tempo/loki), `Makefile` (`make test | up | down`). Goal: `docker compose up --build` boots the empty stack.

## Phase C — Backend core (FR-1 partial, §6)
7. Env config loader for the §5 variable table (fail-fast on required: ADMIN_*, SESSION_SECRET, AGENT_TOKEN, BASE_URL).
8. SQLAlchemy models: `rooms`, `members`, `items`, `sweeper_runs`, `agent_actions` (SQLite WAL).
9. Room ID generator (base62 ≥22 chars, SR-1) + `GET /api/health`.

## Phase D — Auth & operator roles (FR-3, FR-4, FR-6, FR-7 → AC1, AC3, AC4)
10. Admin/guest login: argon2id/bcrypt, constant-time verify, generic errors, HttpOnly/Secure/SameSite=Lax 12h session, server-side logout.
11. Login rate limit 5/15min/IP → 429 (injectable clock); `AGENT_TOKEN` guard; guest rules (one active room → 409, delete-own-room only).

## Phase E — Room lifecycle (FR-1, FR-2, FR-19 → AC1, AC2)
12. `POST /api/rooms` (TTL 1h/24h/7d, share_url); 401 unauthenticated; capability 404 semantics (generic 404, never 403 on member routes); TTL activity extension; room termination deletes files, members get 404.

## Phase F — Member identity (FR-8–FR-11 → AC5)
13. Join validation (name 1–20 trimmed), member token flow (client 32-byte hex, server stores SHA-256 only — SR-2), deterministic color palette.

## Phase G — Content items (FR-12–FR-15, SR-5 → AC6, AC7, AC8)
14. Text clips (1–10k chars, newest-first); file uploads (10 MB cap, allowlist deny-by-default, no SVG, attachment + nosniff serving); delete-own-only via hashed-token compare (403 on mismatch, no broadcast).

## Phase H — WebSocket sync & presence (FR-16–FR-18, SR-7 → AC6, AC9, AC10)
15. One-time 60s WS tickets; full-state-on-connect; broadcast events; 30s heartbeats; 5-min idle drops presence only; client reconnect backoff 1s→30s.

## Phase I — Sweeper (FR-20 → AC11)
16. APScheduler hourly job: delete expired rooms + disk dirs + orphaned files; record runs in `sweeper_runs`.

## Phase J — Security hardening (SR-3, SR-4, SR-6 → AC2, AC17 partial)
17. All rate limits → 429; CORS lock; security headers; CSRF custom header; log/trace/metric redaction (`room_uuid` surrogate only).

## Phase K — Frontend (criteria: Application → AC5, AC6, AC9, AC12)
18. Operator login page; admin dashboard (room list, stats, force-terminate); guest flow.
19. Room page: join screen → live canvas (clips + file cards, "added by ⟨name⟩" in color, relative time), add/upload/delete-own, presence list, WS client with reconnect, localStorage identity.

## Phase L — Testing (criterion: Testing → AC14)
20. Backend unit (IDs, expiry, uploads, ownership, auth, guest rules, rate limits, WS broadcast) + integration full-journey + frontend Vitest — all green via single `make test`. Tests written alongside each phase; this phase closes gaps + wires the single command.

## Phase M — Observability & alerts (criteria: Observability, Alerting → AC17, AC18)
21. OTel spans on upload→validate→store→broadcast → Tempo; Prometheus metrics; JSON logs with `trace_id` → Loki; Grafana dashboards; no room IDs/tokens/names/filenames in telemetry.
22. Alertmanager + `UploadErrorSpike` and `SweeperStalled` → `POST /api/agent/on-alert`; Mailpit email path.

## Phase N — On-call agent (criterion: On-Call Agent → AC19)
23. Alert webhook receiver → Loki diagnosis (deterministic fallback required) → remediation (upload restart / sweeper re-trigger) + synthetic re-test + escalation; records in `agent_actions`.

## Phase O — CI/CD + deploy (criteria: CI/CD, Deployment → AC15, AC16)
24. `ci.yml` (lint+tests per PR), `deploy-dev.yml` (auto + health smoke), `deploy-prod.yml` (manual dispatch + approval), `rollback.yml`. *Decision point with you: deploy target (Fly.io / Render / VPS) or documented-demo fallback.*
25. Update README (setup, demo, manual acceptance script); final self-report against SPECS.md §10 AC1–AC19, all issues closed.

Out of scope throughout: §11 items (E2E encryption, room passwords, Postgres, etc.).