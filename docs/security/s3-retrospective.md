# S3 Retrospective

- **Date:** 2026-09-18
- **Format:** individual, written
- **Sprint:** S3

---

## What went well

1. **The 404-not-403 pattern is simple to apply and easy to prove.**
   Putting the ownership filter inside the same query as the id filter
   means there is only one place to get it wrong.

2. **The hygiene test caught every missing audit entry.** Six times
   across the sprint, a new route triggered the check and forced a
   documentation decision. That is exactly the intended friction.

3. **ADR-0003 resolved the role-refresh question with a real
   implementation, not a hand-wave.** The version check is one
   indexed column and works in the same request path as the JWT.

4. **CI needed only two changes across the whole sprint** — trigger
   on `sprint/**` and make semgrep blocking. Everything else carried
   over from S1 and S2.

## What did not go well

1. **Python 3.14 keeps breaking installs.** `psycopg2` on S0,
   `semgrep` on S3 Day 9. Each one cost time. Downgrading to Python
   3.12 would have removed the entire class of problem.

2. **The container was stopped at the start of Day 9 and produced
   39 spurious failures.** No preflight check exists.

3. **The Day 7 commit missed two files** because `git status --short`
   was not run before the commit. The tag pointed at an incomplete
   commit until it was moved.

4. **The audit chain requires a backfill script** for existing rows.
   The migration added the columns with placeholder values; the
   chain only became valid after the script ran.

5. **The requirements.txt change after semgrep install was almost
   missed.** The click downgrade was fine but not anticipated.

## Action items for S4

| # | Action | Applied in |
|---|--------|-----------|
| 1 | Downgrade the local venv to Python 3.12 to match CI | S4 Day 1 |
| 2 | Add a conftest fixture that fails fast if the backend is down | S4 Day 1 |
| 3 | Run `git status --short` before every commit and before every tag | S4 onward |
| 4 | Commit at the end of every task, not the end of the day | S4 |
| 5 | Any schema change that adds NOT NULL columns needs a backfill script in the same commit | S4 onward |
| 6 | Extend the hygiene check to cover the audit table | S4 if new routes are added |
| 7 | Prefer script files to inline curl for anything longer than one line | S4 |

## Questions to carry forward

- Should the audit chain have a periodic witness — a hash of the
  latest `self_hash` published somewhere outside the DB? Without one,
  deletion of the tail is undetectable.
- The `WWW-Authenticate` header on 401 is sent. Should the client
  treat it specially? Currently it is ignored.
- ADR-0003 mentions caching `role_version` in Redis. Is that worth
  doing before S14? If request volume is low, no.
- The supervisor scope is team-scoped. When a supervisor moves teams,
  the `team_id` in the DB changes but the JWT still carries the old
  role claim. Does the supervisor see their new team immediately, or
  after the token expires? Check whether the team scope reads from the
  DB user or from the JWT. Resolve in S4.
