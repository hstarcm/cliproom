# AGENTS.md — instructions for AI agents working on ClipRoom

ClipRoom is a self-hosted, ephemeral, live shared scratch room app (text clips +
file uploads behind unguessable URLs, real-time WebSocket sync, automatic
expiry). **[SPECS.md](SPECS.md) is the authoritative specification, written
before any code.**

## Where everything lives (modular docs)

| Doc | Read it for |
|---|---|
| [SPECS.md](SPECS.md) | The contract. §3 = functional requirements (FR-1…FR-20), §4 = security requirements (SR-1…SR-7), §10 = acceptance criteria (AC1–AC19), §11 = out of scope |
| [docs/process.md](docs/process.md) | How work flows: spec → tracker issues → implement → review → close. Commit conventions and definition of done |
| [docs/teams.md](docs/teams.md) | The agent team (Spec, Implementer, Test writer, Reviewer, DevOps, On-call) and handoffs |
| [docs/api.md](docs/api.md) | REST + WebSocket contract, error semantics, data model |

## Non-negotiable rules for every agent

1. **Work only against tracker issues.** Every issue is one acceptance
   criterion (AC1–AC19) with its FR/SR references. Commits reference the issue
   (`refs #N`, or `closes #N` when the AC is met). If work has no issue, stop
   and create/ask for one first.
2. **§3 FR / §4 SR are canonical.** If code and SPECS.md disagree, SPECS.md
   wins. Never weaken a security requirement (404-not-403 for rooms, hashed
   tokens, rate limits, log redaction) without updating SPECS.md first.
3. **Never log, trace, or metric:** room IDs, member tokens, member names,
   original filenames, passwords. Use the `room_uuid` surrogate for
   correlation (SR-4).
4. **Do not build §11 items** (read-only links, E2E encryption, room
   passwords, Postgres, multi-node, …). They are out of scope by decision.
5. **Self-report against §10** when your issue is done: which AC bullets are
   verifiably met, and how (test name, command, or manual check).
6. One command must always work: `make test` (backend unit + integration +
   frontend). `docker compose up --build` must boot the full stack.

## Quick orientation

- Backend: `backend/` — Python 3.12, FastAPI, SQLAlchemy 2, SQLite (WAL),
  APScheduler sweeper, native WebSockets.
- Frontend: `frontend/` — React 18 + Vite + TypeScript, Vitest.
- Ops: `docker-compose.yml`, Makefile, `.github/workflows/`.
- Observability: OTel → Tempo (traces), Prometheus (metrics), Loki (logs),
  Grafana (UI); Alertmanager → on-call agent (§7 of SPECS.md).
