# S6 — Endpoint Authorization Matrix

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 6)
- **Related:** ADR-0003, `docs/security/s3-tenant-audit.md`, `threat_register.md`

Every route in the API, with the authorization it enforces. The
`tests/test_endpoint_hygiene.py` check fails if a new route is added
without an entry here.

---

## Legend

| Column | Meaning |
|--------|---------|
| **Auth** | Which roles may call the endpoint. `public` = no token. |
| **Tenant scope** | How the tenant filter is applied. `principal` = from the JWT. `n/a` = not tenant-scoped. |
| **Resource scope** | What resource the caller may act on. `self` = own rows. `team` = same team. `tenant` = all rows in the tenant. |
| **Enforcement** | The specific mechanism. |

---

## Public

| Method | Path | Auth | Tenant scope | Resource scope | Enforcement |
|--------|------|------|--------------|----------------|-------------|
| GET | `/health` | public | n/a | n/a | none — meta only |
| POST | `/api/v1/auth/login` | public | n/a | n/a | rate limit 10/min (staging/prod) |

## Authenticated — any role

| Method | Path | Auth | Tenant scope | Resource scope | Enforcement |
|--------|------|------|--------------|----------------|-------------|
| GET | `/api/v1/auth/me` | any | principal | self | `get_current_user` |
| POST | `/api/v1/auth/logout` | any | principal | self | `get_current_user` |
| POST | `/api/v1/devices/register` | any | principal | self | `active_devices_for_self` |
| GET | `/api/v1/devices/me` | any | principal | self | `active_device_for_self` |
| POST | `/api/v1/attendance/events` | any | principal | self | `active_device_for_self` |
| GET | `/api/v1/attendance/events` | any | principal | self | `events_for_self` |
| GET | `/api/v1/attendance/events/{event_id}` | any | principal | self | `get_own_event_or_404` |

## Supervisor and above

| Method | Path | Auth | Tenant scope | Resource scope | Enforcement |
|--------|------|------|--------------|----------------|-------------|
| GET | `/api/v1/attendance/team/events` | supervisor | principal | team | `events_for_team` + `team_id is not None` |
| GET | `/api/v1/attendance/team/events/{event_id}` | supervisor | principal | team | `get_team_event_or_404` |

## HR / Sys Admin

| Method | Path | Auth | Tenant scope | Resource scope | Enforcement |
|--------|------|------|--------------|----------------|-------------|
| GET | `/api/v1/attendance/admin/summary` | hr_ops, sys_admin | principal | tenant | `require_role` + `events_for_tenant` |

## Sys Admin only

| Method | Path | Auth | Tenant scope | Resource scope | Enforcement |
|--------|------|------|--------------|----------------|-------------|
| GET | `/api/v1/audit/verify` | sys_admin | cross-tenant by design | metadata only | `require_role(ROLE_SYS_ADMIN)` |

## Lab-only (ENVIRONMENT=lab)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/lab/sqli/search` | public | intentionally vulnerable |
| GET | `/api/v1/lab/bola/events/{event_id}` | any | intentionally vulnerable |
| POST | `/api/v1/lab/xxe/parse` | public | intentionally vulnerable |
| POST | `/api/v1/lab/pickle/load` | public | intentionally vulnerable |
| GET | `/api/v1/lab/ssrf/fetch` | public | intentionally vulnerable |

Lab routes are never mounted in staging or prod. `app/main.py`
conditions the `include_router` calls on `_settings.is_lab`.

---

## Rules that produced this matrix

1. **Tenant scope comes from the principal, never the request.**
   `tenant_id` in a body or query parameter is ignored.
2. **Resource scope is enforced in the same query as the id filter.**
   See `get_own_event_or_404`.
3. **Role checks run before tenant filters.** A 403 beats a 404.
4. **The 404-not-403 pattern** is used where a 403 would leak resource
   existence: cross-user reads, cross-team reads.

---

## How to add a new endpoint

1. Add a row to this matrix.
2. Add a row to `docs/security/s3-tenant-audit.md`.
3. Use a helper from `app/core/tenant.py` or `app/core/not_found.py`.
4. Write a test that proves the boundary in both directions (allowed
   and denied).
5. `tests/test_endpoint_hygiene.py` will fail if step 1 is skipped.

---

## S7 — Workforce Analytics (in progress)

No endpoints yet. Tables added on S7 Day 1:

- `shifts`
- `shift_assignments`
- `leave_types`
- `leave_requests`
- `lop_records`

Rows will be added here as endpoints are created. The
`tests/test_endpoint_hygiene.py` check will fail if a new route is
added without an entry in the audit table.
