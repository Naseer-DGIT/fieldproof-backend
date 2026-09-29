# S3 Tenant Isolation Audit

Every database access in `app/` and whether it enforces tenant scope.

| Endpoint | Query | Filter | Safe? |
|----------|-------|--------|-------|
| POST /auth/login | `User.email == body.email` | resolves by email; JWT carries `tenant` | yes (login path) |
| GET /auth/me | `db.get(User, sub)` | id is from the signed JWT | yes |
| POST /devices/register | `Device.user_id == user.id` | user from JWT | yes |
| GET /devices/me | `Device.user_id == user.id` | user from JWT | yes |
| POST /attendance/events | `_active_device(user)` → `Device.user_id == user.id` | user from JWT | yes |
| GET /attendance/events | `AttendanceEvent.user_id == user.id` | user from JWT | yes |
| GET /attendance/events/{event_id} | `get_own_event_or_404(db, user, event_id)` | id + owner in one query | yes |
| GET /attendance/team/events | `events_for_team(db, user)` | `User.tenant_id` AND `User.team_id` in one query | yes |
| GET /attendance/team/events/{event_id} | `get_team_event_or_404(db, user, event_id)` | id + tenant + team in one query | yes |
| GET /attendance/admin/summary | `User.tenant_id == user.tenant_id` | tenant from JWT | yes |

| POST /shifts | `shifts_for_tenant(db, user)` for the duplicate-name check; insert sets `tenant_id=user.tenant_id` | tenant from principal | yes |
| GET /shifts | `shifts_for_tenant(db, user)` | tenant from principal | yes |
| POST /shifts/assignments | `shifts_for_tenant` + `shift_assignments_for_tenant` + explicit user lookup filtered by `tenant_id` | tenant from principal | yes |
| GET /shifts/assignments | `shift_assignments_for_tenant(db, user)`; employees additionally filtered by `user_id == user.id` | tenant from principal | yes |

| POST /leave/types | `leave_types_for_tenant(db, user)` for duplicate check; insert uses `tenant_id=user.tenant_id` | tenant from principal | yes |
| GET /leave/types | `leave_types_for_tenant(db, user)` | tenant from principal | yes |
| POST /leave/requests | `leave_types_for_tenant(db, user)`; insert uses `tenant_id=user.tenant_id` | tenant from principal | yes |
| GET /leave/requests | `leave_requests_for_tenant(db, user)`; employees additionally filtered by `user_id == user.id` | tenant from principal | yes |
| POST /leave/requests/{request_id}/decision | `leave_requests_for_tenant(db, user)` | tenant from principal | yes |
| POST /leave/requests/{request_id}/cancel | `leave_requests_for_tenant(db, user)` | tenant from principal | yes |
| POST /lop/compute | `compute_for_range(db, user.tenant_id, ...)` | tenant from principal | yes |
| GET /lop | `lop_records_for_tenant(db, user)` | tenant from principal | yes |
## Rules

1. `tenant_id` in a request body or query parameter is never trusted.
   The only source is `get_current_user().tenant_id`.
2. Every repository or query helper that reads tenant-scoped data takes
   a `User` (or a `tenant_id: int` derived from one) as its first
   argument, not a request-supplied value.
3. A resource fetched by id must include `tenant_id` in the WHERE
   clause. Fetching first and checking the tenant afterward is a race
   condition and is rejected in review.

## Gaps for later sprints

- No supervisor-scoped read path yet. When one is added, the query must
  filter by `User.tenant_id == user.tenant_id` **and** the supervisor's
  team/site scope. Day 3 does not cover this; it is S7 work.

## Day 3 — note on tagging

The `s3-day3` tag was moved after the initial push because the audit
doc commit landed before the code commit. Both are now in the same
Day 3 range.

Rule for later days: run `git status --short` before `git tag`. If
anything is uncommitted, commit it first. A tag promises a reproducible
state.

## Day 4 — supervisor scope

Added `team_id` (nullable integer) to `users`. Teams are scoped inside
a tenant: two tenants may both have team 1001, and they are different
teams.

Added `events_for_team(db, user)` in `app/core/tenant.py`. It filters
on `User.tenant_id == user.tenant_id AND User.team_id == user.team_id`
in a single query.

Added `GET /attendance/team/events`:
- supervisor with a team → team-scoped list
- supervisor with no team → 403
- any other role → 403
- anonymous → 401

Tests in `tests/test_supervisor_scope.py`:
- supervisor A sees team A's events, not team B's
- supervisor B sees team B's events, not team A's
- supervisor with no team → 403
- employee → 403
- supervisor in a different tenant with the same team id → empty
- anonymous → 401

## Day 4 — rule for scope additions

Every new scope (self, team, tenant, org) gets:
1. A helper in `app/core/tenant.py` with the scope filter in one query
2. A row in this audit
3. A test that proves the boundary in both directions

## Day 5 — supervisor resource IDs and role refresh

Added `GET /attendance/team/events/{event_id}` with
`get_team_event_or_404`. Returns 404 for events in another team, in
another tenant, or that do not exist. Bodies identical.

Added `role_version` column to `users`. JWT now carries `rv`. Every
authenticated request compares the claim to the row and returns 401
when they differ. See ADR-0003.

Tests:
- `tests/test_role_refresh.py` — 4 tests
- `tests/test_supervisor_idor.py` — 4 tests

## Day 6 — authorization audit log

Added `authorization_events` table. One row per 401, 403, and 404.
Columns: `user_id`, `tenant_id`, `status_code`, `reason`, `method`,
`endpoint`, `created_at`.

No PII. No request body, query string, headers, or IP. The table
answers "who was denied what, and why" — nothing else.

Wired via a FastAPI `HTTPException` handler in `app/main.py`. The
handler calls `record_denial`, then returns the same response FastAPI
would have returned. A failure to write the audit row is logged and
swallowed; it never changes what the caller sees.

`get_current_user` now sets `request.state.user_id` and
`request.state.tenant_id` after resolving the principal. The handler
reads those without a second DB read.

Tests in `tests/test_audit_log.py`:
- 401 without a token → one row, null user
- 403 with a token → one row with user and tenant
- 404-not-403 → one row with reason "Event not found"
- 200 → no row
- stale-token 401 → one row

## Day 7 — /audit/verify is cross-tenant by design

`GET /api/v1/audit/verify` is sys_admin-only. It walks the entire
authorization_events table without a tenant filter — that is the point:
a chain break must be visible across tenants, not hidden per tenant.

It returns metadata only:
- `rows_checked` (integer)
- `breaks` (list of `{id, reason}` for the first mismatch)
- `ok` (boolean)

It does not return row contents: no `user_id`, no `tenant_id`, no
`reason`, no `endpoint`. There is no per-tenant data to leak, so there
is no tenant filter to audit.

`tests/test_endpoint_hygiene.py` allowlists this endpoint via
`ALLOWED_UNGATED`. Any change that makes this endpoint return row
contents must remove the allowlist entry and add a row to the table
above.

## S7 Day 1 — shift and leave tables

New tables, all tenant-scoped:

| Table | Tenant column | Helper |
|-------|--------------|--------|
| `shifts` | `tenant_id` | `shifts_for_tenant` |
| `shift_assignments` | `tenant_id` | `shift_assignments_for_tenant`, `shift_assignments_for_self` |
| `leave_types` | `tenant_id` | `leave_types_for_tenant` |
| `leave_requests` | `tenant_id` | `leave_requests_for_tenant`, `leave_requests_for_self` |
| `lop_records` | `tenant_id` | `lop_records_for_tenant`, `lop_records_for_self` |

Every table has `tenant_id NOT NULL` with `ondelete="CASCADE"` from
`tenants`. Every helper filters on `user.tenant_id`. No endpoint reads
these tables yet; the helpers are ready for S7 Day 2+.
