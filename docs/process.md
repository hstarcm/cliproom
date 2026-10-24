# Working process: spec → issues → implement → review → close

## 1. Source of truth

SPECS.md is the authoritative specification (§3 functional, §4 security,
§10 acceptance criteria, §11 out of scope). It was written before any code.
If reality demands a change, the Spec agent updates SPECS.md **first**, in its
own commit, then the implementation follows.

## 2. Tracker

All work is tracked in GitHub Issues (public). One issue per acceptance
criterion (AC1–AC19), labeled `backend` / `frontend` / `devops` /
`observability` / `testing`. An issue's body is its acceptance criteria —
verbatim from SPECS.md §10 plus the related FR/SR IDs.

## 3. Branch & commit conventions

- Branch per issue: `ac3-login-rate-limit` style (`ac<N>-slug`).
- Commit messages: `area: summary (refs #N)`; use `closes #N` only when the AC
  is verifiably met.
- Commits must never contain room IDs, member tokens, names, filenames, or
  credentials (SR-4) — including in test fixtures.

## 4. Definition of done (per issue)

1. Code implements the FR/SR IDs listed in the issue.
2. Tests cover the behavior (§9 map) and pass locally: `make test`.
3. A comment on the issue self-reports against §10: which bullets are met and
   how verified (test name / command / manual check).
4. Reviewer role has checked §4 security implications.
5. PR merged to main; issue auto-closes via `closes #N`.

## 5. Milestones

| Order | Block | Issues |
|---|---|---|
| 1 | Scaffold + containerization | AC13, AC14 (partial) |
| 2 | Auth, rooms, members, content, WS, sweeper | AC1–AC12 |
| 3 | Observability + alerting + on-call agent | AC17–AC19 |
| 4 | CI/CD + deployment + final self-report | AC15, AC16 |

## 6. Escalation

Anything that would require weakening an SR, logging sensitive data, or
building a §11 item: stop, comment on the issue, and route to the Spec agent
(= ask the maintainer).
