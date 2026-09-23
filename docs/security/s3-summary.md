# S3 — RBAC & Tenant Isolation: Sprint Summary

- **Sprint:** S3 (Days 1–10)
- **Branch:** `sprint/s3-rbac`
- **Dates:** 2026-09-17 → 2026-09-18
- **Related:** ADR-0003, threat_register.md

## Deliverables

| Day | Deliverable |
|-----|-------------|
| 1 | RBAC module, admin summary, 401-not-422 |
| 2 | Tenant query helpers, cross-tenant tests, hygiene check, backend CI |
| 3 | 404-not-403 pattern, IDOR coverage |
| 4 | Supervisor scope with team_id |
| 5 | Supervisor IDOR, role_version refresh (ADR-0003) |
| 6 | Authorization audit log (401/403/404) |
| 7 | Hash chain on audit trail, verify endpoint, retention script |
| 8 | Security review |
| 9 | Semgrep blocking, test count guard |
| 10 | Summary, retrospective, PR, tag |

## Verification

- `pytest -q` → 39 tests passing
- `verify_chain()` → breaks: []
- CI green, semgrep blocking on app/

## Accepted limitations

1. role_version costs one indexed read per request (S14 caching candidate)
2. Audit chain detects modification, not deletion (S14 witness)
3. Test-only chain restoration uses the backfill script

## Metrics

- Commits: 17
- Test files: 8
- Tests: 39
- Endpoints added: 4
- Threats closed: T-006, T-007, T-008, T-015
