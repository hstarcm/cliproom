# Agent team specification

From SPECS.md §8. The team is role-based; one human or AI assistant may hold
several roles, but every contribution must be attributable to a role (commit
trailers or issue comments declare it).

| Agent | Responsibility | Hands off to |
|---|---|---|
| **Spec agent** | Maintains SPECS.md; turns requirements into tracker issues (one AC per issue) with acceptance criteria; arbitrates spec-vs-code conflicts (SPECS.md wins) | Implementer |
| **Implementer** | Writes backend/frontend code against issues; references issue IDs in every commit (`refs #N` / `closes #N`) | Test writer, Reviewer |
| **Test writer** | Owns pytest unit + integration and Vitest suites; red-green for every FR (SPECS.md §9) | Reviewer |
| **DevOps agent** | Dockerfiles, docker-compose, CI/CD workflows, observability config, deploy + rollback | Reviewer |
| **On-call agent** | Runtime responder (SPECS.md §7): wakes on Alertmanager webhook, diagnoses via Loki, remediates, records in `agent_actions`. A shipped artifact of the product, not a dev-time role | — |

## Handoff contract

- Spec → Implementer: issue body carries the AC text + FR/SR IDs; nothing is
  implemented without an issue.
- Implementer → Test writer: code lands behind feature branches; tests must
  exist or be written before the issue closes.
- Test writer / DevOps → Reviewer: PRs link their issue; Reviewer checks the
  diff against SPECS.md §3/§4 (security especially: 404-vs-403, hashed tokens,
  rate limits, log redaction).
- Reviewer → Implementer: fix loop on the same PR until clean; only then may
  the issue close.

## Evidence that agents used the tracker

- Every commit references an issue number.
- Progress/self-reports are posted as issue comments (which AC bullets are met
  and how they were verified).
- PR descriptions link issues; the GitHub tracker is the public record.
