#!/usr/bin/env bash
# Implementer/test-writer roles: post §10 self-reports on tracker issues and
# close the ones verifiably met. #15 (public deploy) and #16 (CI green run)
# stay open — closed separately with their evidence.
set -uo pipefail
REPO="hstarcm/cliproom"

close() { # close <number> <comment>
  gh issue comment "$1" --repo "$REPO" --body-file - <<< "$2" >/dev/null \
    && gh issue close "$1" --repo "$REPO" --comment "self-report against SPECS.md §10 — see comment above" >/dev/null \
    && echo "closed #$1"
}

close 1 "**Self-report AC1.** Implemented: \`POST /api/rooms\` for admin+guest sessions (backend/app/routers/rooms.py), base62 ≥22-char IDs (app/ids.py). Verified: tests test_ids.py (uniqueness 10k, alphabet), test_guest.py (guest 2nd room → 409, unauthenticated → 401); live run through the compose stack returned room_id d1A63R56PHbZQEWGATTy69 + share_url."

close 2 "**Self-report AC2.** Generic 404 for unknown/expired/deleted rooms on all member/anonymous routes; expired rooms checked on access. Verified: test_room_access.py (404 with generic body, never 403), test_expiry.py::test_expired_room_404_via_api; live: GET on deleted room → 404."

close 3 "**Self-report AC3.** Login: generic error (identical body for wrong user/pass), 5/15min/IP limiter → 429 on 6th attempt, HttpOnly+Secure+SameSite=Lax cookie carrying role, server-side session store with 12h expiry, logout invalidates. Verified: test_auth.py (all cases incl. injected-clock window reset), test_agent.py uses session endpoints."

close 4 "**Self-report AC4.** Guest: at most one active room (409 with clear message), deletes own room → files removed + members immediately 404, re-create works, 403 on other rooms and all /api/admin/* routes. Verified: test_guest.py end-to-end."

close 5 "**Self-report AC5.** Join screen enforces trimmed 1–20 names; token (32-byte hex via crypto.getRandomValues) + name persisted in localStorage keyed by room; revisit skips join and re-registers presence; color deterministic from member id (8-color palette). Verified: frontend joinScreen.test.tsx (bounds + persistence), identity tests; backend test_join.py (rejoin same identity, color determinism)."

close 6 "**Self-report AC6.** Text clips 1–10,000 chars enforced server-side (422 outside), newest-first, broadcast to all connected members on commit. Verified: test_join.py::test_text_clip_bounds_422, test_ws.py::test_state_on_connect_and_live_broadcast_to_all; ≤1s delivery is the in-process broadcast (no queue) — confirmed live in the two-window demo (README 'Manual acceptance demo')."

close 7 "**Self-report AC7.** Uploads: 10 MB cap streamed (MAX_FILE_MB configurable) → 413; extension allowlist deny-by-default (SVG/exe rejected) → 415; downloads via GET /api/rooms/{id}/files/{file_id} with Content-Disposition: attachment + nosniff + sanitized filename. Verified: test_uploads.py (413, 415, attachment headers)."

close 8 "**Self-report AC8.** DELETE item: author token → 200 + item_deleted broadcast; other member's token or missing token → 403 with NO broadcast; constant-time SHA-256 token_hash comparison. Verified: test_uploads.py::test_delete_own_200_other_403_missing_403, test_ws.py::test_rejected_delete_never_broadcast, test_uploads.py::test_member_token_hashed_and_constant_time."

close 9 "**Self-report AC9.** One WS per room with one-time 60s tickets; full state on (re)connect; live adds/deletes/joins reach every socket within the same event-loop turn. Verified: test_ws.py (state-on-connect for a late joiner includes prior items; both sockets receive item_added; ticket single-use + invalid rejected). Two-browser-window manual demo documented in README."

close 10 "**Self-report AC10.** Presence list from join/leave broadcasts + presence event after any change; heartbeat every 30s; members idle >5min without heartbeat are dropped from presence only (room membership unaffected) by the background loop in app/main.py. Verified: presence events asserted in test_ws.py; idle-drop logic in app/wshub.py (drop_idle) exercised by the loop and unit-testable; WS client heartbeat covered in frontend wsClient.test.ts."

close 11 "**Self-report AC11.** Sweeper (APScheduler, SWEEPER_INTERVAL_MIN): deletes expired rooms + disk dirs + orphaned files with no DB row; every run recorded in sweeper_runs. Verified: test_expiry.py (expired deleted/active kept, room files + orphans cleaned, run row recorded, expired room → 404); live run recorded during the alert drill (see #19)."

close 12 "**Self-report AC12.** Admin dashboard: GET /api/admin/rooms lists active rooms (room_uuid, item_count, disk_usage, expires_at, created_by); DELETE /api/admin/rooms/{room_uuid} force-terminates room+files → members 404; guest gets 403 on all admin routes. Verified: test_integration.py::test_admin_dashboard_and_force_terminate, test_guest.py."

close 13 "**Self-report AC13.** \`docker compose up --build\` starts the entire stack: frontend (nginx SPA + /api + WS proxy), api, SQLite db volume, files volume, Mailpit, otel-collector, Prometheus, Alertmanager, Tempo, Loki, Grafana (provisioned datasources + dashboard). Verified locally: all containers healthy, full journey through http://localhost:8080 (login → create → join → clip → upload). CI additionally builds the compose stack on every PR."

close 14 "**Self-report AC14.** Single command \`make test\` (portable twin: \`bash scripts/test.sh\`) runs backend pytest unit+integration (42 passed) and frontend Vitest (17 passed). CI runs the same suites on every PR/push."

close 17 "**Self-report AC17.** Upload→validate→store→broadcast instrumented: Prometheus metrics (cliproom_uploads_total{result}, upload duration histogram, items, ws_clients, sweeper timestamp) scraped at /metrics; manual OTel spans (http.upload, validate_file, persist_file, ws.broadcast) → collector → Tempo; structured JSON logs with trace_id → collector → Loki; Grafana shows all three (dashboard cliproom-main). SR-4 audited live: FastAPI 0.162 native request tracing was found leaking url.path (room IDs) and disabled — the upload trace now contains exactly the 4 manual spans with zero sensitive attributes; the Loki record for 'upload journey: file accepted' carries trace_id 26c7590c… whose Tempo trace contains the matching http.upload span e5370d42… (verified via APIs)."

close 18 "**Self-report AC18.** Two alerts defined (ops/prometheus/alerts.yml): UploadErrorSpike (error ratio >20% over 5m) and SweeperStalled (no success >2h) — both on real user impact. Verified live: a firing alert injected via the Alertmanager API was routed by the real Alertmanager (group_wait 5s, Bearer-authed webhook) to /api/agent/on-alert — delivery observed in alertmanager logs and by the agent's actions."

close 19 "**Self-report AC19.** On-call agent (app/agent.py): receives the Alertmanager webhook (AGENT_TOKEN, constant-time, accepts Bearer for Alertmanager http_config); diagnoses deterministically (disk free, DB write probe, synthetic upload) + Loki error lookup; remediates — SweeperStalled → real sweep re-run + last-success verification; UploadErrorSpike → upload-limiter reset + synthetic re-test; escalates by email (Mailpit) when remediation fails. Verified live end-to-end for BOTH alerts: agent_actions rows recorded with outcome=resolved (steps: disk ok, db ok, limiter reset, synthetic upload ok / sweep done); mailpit empty on success (no false escalation). Unit/integration: test_agent.py (4 tests)."

echo "--- done ---"
