#!/usr/bin/env bash
# Spec agent: creates the public tracker (GitHub Issues) from SPECS.md §10.
# One issue per acceptance criterion AC1–AC19. Re-running would duplicate
# issues — do not re-run blindly.
set -uo pipefail

REPO="hstarcm/cliproom"

# --- labels -----------------------------------------------------------------
for lbl in backend:1D76DB frontend:0E8A16 devops:5319E7 observability:FFA500 testing:D93F0B; do
  name="${lbl%%:*}"; color="${lbl##*:}"
  gh label create "$name" --repo "$REPO" --color "$color" --force 2>/dev/null >/dev/null \
    && echo "label ok: $name" || echo "label skipped: $name"
done

# --- issues -----------------------------------------------------------------
create() { # create <title> <labels> <body>
  gh issue create --repo "$REPO" --title "$1" --label "$2" --body-file - <<< "$3"
}

create "AC1 — Room creation by admin & guest (≥22-char base62 ID; 401 unauth; 409 guest 2nd room)" "backend,testing" \
"**Acceptance criterion AC1 (SPECS.md §10)**

> Admin **and** guest sessions can each create a room returning a share URL with a ≥22-char base62 ID; unauthenticated create → 401; guest second active room → 409.

**Related requirements:** FR-1, FR-3, FR-7, SR-1
**Scope:** \`POST /api/rooms\` (admin/guest session), room ID generator, guest one-active-room rule.
**Definition of done:** per docs/process.md §4 (code + tests green in \`make test\` + self-report comment here)."

create "AC2 — Capability 404 semantics (unknown/expired/deleted room → generic 404, never 403)" "backend,testing" \
"**Acceptance criterion AC2 (SPECS.md §10)**

> Valid room URL → room page; unknown/expired/deleted ID → generic 404 (never 403, no stack info) for members and anonymous visitors.

**Related requirements:** FR-2, SR-1
**Scope:** all member/anonymous routes; generic body; no stack traces."

create "AC3 — Login security (generic errors; 6th attempt/15 min → 429; HttpOnly/Secure/SameSite=Lax cookie; server-side logout)" "backend,testing" \
"**Acceptance criterion AC3 (SPECS.md §10)**

> Login: wrong password → generic error; 6th attempt in 15 min → 429; successful login sets HttpOnly/Secure/SameSite=Lax cookie with role; logout invalidates server-side.

**Related requirements:** FR-3, FR-4, SR-3, SR-7
**Scope:** \`POST /api/admin/login\`, \`POST /api/admin/logout\`, login rate limiter (injectable clock), session store."

create "AC4 — Guest constraints (delete own room → members 404, re-create works; 403 on other rooms & admin routes)" "backend,testing" \
"**Acceptance criterion AC4 (SPECS.md §10)**

> Guest can delete its own room (members then get 404, files gone, re-create works); guest gets 403 on other rooms and all admin routes.

**Related requirements:** FR-5, FR-7
**Scope:** \`DELETE /api/rooms/{room_uuid}\` role checks, guest one-room lifecycle."

create "AC5 — Join screen & persistent identity (1–20 char name; localStorage name+token; revisit skips join; stable color)" "frontend,backend,testing" \
"**Acceptance criterion AC5 (SPECS.md §10)**

> First visit enforces 1–20 char name; name + token persist in localStorage; revisit skips join; returning member keeps name and color.

**Related requirements:** FR-8, FR-9, FR-10, FR-11, SR-2
**Scope:** join screen UI + validation, \`POST /api/rooms/{room_id}/join\`, member token generation (crypto.getRandomValues), server-side SHA-256 token_hash, deterministic palette."

create "AC6 — Text clips (1–10k chars enforced; visible to all connected members ≤1 s)" "backend,frontend" \
"**Acceptance criterion AC6 (SPECS.md §10)**

> Any member adds a text clip (1–10k chars enforced); visible to all connected members ≤1 s.

**Related requirements:** FR-12, FR-14, FR-16
**Scope:** \`POST /api/rooms/{room_id}/items/text\` server-side validation, newest-first ordering, WS broadcast."

create "AC7 — File uploads (≤10 MB, allowlist only; 413/415; downloads as attachments with safe headers)" "backend,testing" \
"**Acceptance criterion AC7 (SPECS.md §10)**

> Uploads ≤10 MB and allowlisted types only; violations → clear 413/415; downloads served as attachments with safe headers.

**Related requirements:** FR-13, SR-5
**Scope:** \`POST /api/rooms/{room_id}/items/file\` (MAX_FILE_MB configurable, extension/MIME allowlist, deny-by-default, no SVG), storage under DATA_DIR/<room_id>/<file_id>, Content-Disposition: attachment + nosniff."

create "AC8 — Delete-own-only items (author → 200 + broadcast; others/no-token → 403; rejected deletes never broadcast)" "backend,testing" \
"**Acceptance criterion AC8 (SPECS.md §10)**

> Delete-own items: author → 200 + broadcast; another member's item → 403; no token → 403; rejected deletes never broadcast.

**Related requirements:** FR-15, SR-2
**Scope:** \`DELETE /api/rooms/{room_id}/items/{item_id}\`, SHA-256 token_hash comparison (constant time), file cleanup on delete."

create "AC9 — Live sync in two browser windows (≤1 s) + correct full state on reconnect" "frontend,backend" \
"**Acceptance criterion AC9 (SPECS.md §10)**

> Two browser windows: add/delete/join in one appears in the other ≤1 s; a reconnecting client receives the correct full state.

**Related requirements:** FR-16, FR-17
**Scope:** WS endpoint \`/api/rooms/{room_id}/ws?ticket=\`, one-time 60 s tickets, state-on-connect, client reconnect with exponential backoff (1 s → 30 s)."

create "AC10 — Presence (join/leave updates; idle >5 min without heartbeat dropped from presence only)" "backend,frontend" \
"**Acceptance criterion AC10 (SPECS.md §10)**

> Presence list updates on join/leave; idle member dropped from presence after 5 min without heartbeat (room membership unaffected).

**Related requirements:** FR-18
**Scope:** 30 s heartbeats, idle tracking, member_joined/member_left/presence events, presence UI."

create "AC11 — TTL expiry & sweeper (expired room + files deleted; orphans cleaned; run in sweeper_runs; expired room → 404)" "backend" \
"**Acceptance criterion AC11 (SPECS.md §10)**

> Room past its TTL (no activity extension) is deleted by the sweeper with its files; orphaned files cleaned; run recorded in \`sweeper_runs\`; expired room returns 404.

**Related requirements:** FR-19, FR-20
**Scope:** TTL 1h/24h/7d + activity extension, APScheduler hourly sweeper (SWEEPER_INTERVAL_MIN), orphan detection, sweeper_runs recording."

create "AC12 — Admin dashboard (active rooms + stats; force-terminate deletes room+files; guest 403)" "frontend,backend" \
"**Acceptance criterion AC12 (SPECS.md §10)**

> Admin dashboard lists active rooms with stats; force-terminate deletes room + files immediately; guest blocked (403).

**Related requirements:** FR-5
**Scope:** \`GET /api/admin/rooms\`, \`DELETE /api/admin/rooms/{room_uuid}\`, dashboard UI."

create "AC13 — Single-command stack (docker compose up --build: frontend, api, volumes, mailpit, observability)" "devops" \
"**Acceptance criterion AC13 (SPECS.md §10)**

> \`docker compose up --build\` starts the entire stack (frontend, api, db volume, files volume, mailpit, observability); app fully usable locally with that one command.

**Related requirements:** §5 architecture (compose: frontend nginx, api FastAPI, SQLite volume, DATA_DIR volume, mailpit, otel-collector, grafana/prometheus/tempo/loki)."

create "AC14 — Single-command tests (make test = backend unit + integration + frontend; all pass)" "testing,devops" \
"**Acceptance criterion AC14 (SPECS.md §10)**

> \`make test\` runs backend unit + integration + frontend suites; all pass.

**Related requirements:** §9 testing requirements
**Scope:** pytest unit suites (IDs, expiry, uploads, ownership, auth, guest, rate limits, WS broadcast), full-journey integration test, Vitest suites, Makefile wiring."

create "AC15 — Deployment (public URL reachable, or clear documented demo; rollback path tested once)" "devops" \
"**Acceptance criterion AC15 (SPECS.md §10)**

> Public URL reachable (Fly.io/Render/VPS) — or a clear demo of the deployment documented as fallback; rollback path (redeploy previous image tag) documented and tested once.

**Related requirements:** §10 AC15; rollback workflow."

create "AC16 — CI/CD (CI lint+tests per PR; CD auto-deploy dev on merge + /api/health smoke; manual prod dispatch with approval)" "devops" \
"**Acceptance criterion AC16 (SPECS.md §10)**

> CI: lint + tests on every PR; CD: auto-deploy to dev on merge to main (with \`/api/health\` smoke check); manual \`workflow_dispatch\` deploy to production with reviewer approval.

**Related requirements:** §5 repo layout (.github/workflows: ci.yml, deploy-dev.yml, deploy-prod.yml, rollback.yml)."

create "AC17 — Observability (upload→broadcast in Grafana: metrics + traces + logs sharing trace_id; no sensitive data in telemetry)" "observability,backend" \
"**Acceptance criterion AC17 (SPECS.md §10)**

> Upload→broadcast journey visible in Grafana as metrics + traces + structured logs sharing a \`trace_id\`; telemetry contains no room IDs, tokens, names, filenames, or credentials.

**Related requirements:** §7 observability, SR-4
**Scope:** OTel spans (http.upload, validate_file, persist_file, ws.broadcast) → Tempo; Prometheus metrics; JSON logs → Loki; Grafana dashboards."

create "AC18 — Alert on real user impact (induce failure → Alertmanager fires → email/webhook arrives)" "observability,devops" \
"**Acceptance criterion AC18 (SPECS.md §10)**

> At least one alert fires on real user impact (test: induce the failure → alert arrives via Alertmanager → email/webhook).

**Related requirements:** §7 alerts (UploadErrorSpike, SweeperStalled), Alertmanager → \`POST /api/agent/on-alert\`, Mailpit email."

create "AC19 — On-call agent (wakes on alert, diagnoses + remediates, records in agent_actions, metric returns green)" "observability,backend" \
"**Acceptance criterion AC19 (SPECS.md §10)**

> On-call agent wakes on the alert, performs diagnosis + remediation, records it in \`agent_actions\`, and the failing condition returns to green (verified by metric).

**Related requirements:** §7 on-call responder agent, FR-6 (AGENT_TOKEN)
**Scope:** webhook receiver, Loki diagnosis (deterministic fallback required), remediation (upload restart / sweeper re-trigger + synthetic re-test), escalation email, agent_actions recording."

echo "--- done ---"
