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
