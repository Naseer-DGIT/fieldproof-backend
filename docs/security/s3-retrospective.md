# S3 Retrospective

## What went well

1. 404-not-403 pattern is simple and provable — one query, one message
2. Hygiene test forced a documentation decision on every new route
3. ADR-0003 resolved role refresh with real code, not a hand-wave
4. CI carried over from S1/S2 with only two changes

## What did not go well

1. Python 3.14 keeps breaking installs (psycopg2, semgrep)
2. Stopped container produced 39 spurious test failures
3. Day 7 commit missed two files — no `git status --short` before commit
4. Audit chain needed a backfill for existing rows

## Action items for S4

| # | Action |
|---|--------|
| 1 | Downgrade venv to Python 3.12 to match CI |
| 2 | Add conftest fixture that fails fast when backend is down |
| 3 | Run `git status --short` before every commit and tag |
| 4 | Commit at task boundaries, not end of day |
| 5 | NOT NULL schema changes ship with a backfill script |
| 6 | Prefer script files to inline curl for multi-line commands |

## Questions to carry forward

- Should the audit chain have an external witness?
- Team_id comes from DB user, not JWT — confirm the supervisor move-team case in S4
