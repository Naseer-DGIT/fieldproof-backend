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
