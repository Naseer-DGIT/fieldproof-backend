# S6 Retrospective

- **Date:** 2026-09-28
- **Sprint:** S6

---

## What went well

1. **The ZAP baseline immediately surfaced four header findings.** The
   fix on Day 2 was mechanical and testable.
2. **The manual pentest proved six attacks fail.** Each one has a
   reproducible command and a specific reason it cannot succeed.
3. **The authorization matrix and attack tree are the two most useful
   documents in the sprint.** They make the whole surface visible in
   one place.
4. **The rate limit load test found the concurrent behavior is
   correct.** No race, no bypass via headers.
5. **The CI integration of the authenticated scan is opt-in and
   therefore cheap.** It runs on a label or nightly, not on every push.

## What did not go well

1. **PyPI timeouts blocked two CI runs.** The fix (`--retries 10
   --timeout 60`) is standard but was not in place from day one.
2. **Three tags were created before the work was committed.** The
   `s6-day3`, `s6-day4`, and `s6-dayN` incidents. Each was fixed by
   moving or deleting the tag. The pattern is not new.
3. **The rate-limit test initially broke the full suite.** The test
   needed to be opt-in (`RUN_RATE_LIMIT_TEST=1`) and the dev limit
   needed to be higher than production.
4. **The pentest report was committed with placeholders.** The
   `grep -c "<PASTE"` check exists for a reason.
5. **Uvicorn died repeatedly mid-session.** Every time it did, tests
   failed with `ConnectError` before any assertion ran. The new
   `scripts/start_backend.sh` addresses this.

## Action items for S7

| # | Action | Applied in |
|---|--------|-----------|
| 1 | Add pip retry policy to any new workflow from day one | S7 |
| 2 | Run the placeholder check before every `git commit` on a doc | S7 |
| 3 | Use `./scripts/start_backend.sh` as the first step of any test run | S7 |
| 4 | Any new test that fights another control is opt-in, not default | S7 |
| 5 | Tag only after `git status --porcelain` is empty | S7 |
| 6 | Every new endpoint gets a row in the authz matrix and the tenant audit | S7 |

## Questions to carry forward

- The attack tree has a leaf for `X-Forwarded-For` handling. When the
  app runs behind the ALB in S15, does the proxy preserve the client
  IP at the TCP level? If not, the limiter is keyed on the proxy.
- The ZAP authenticated scan uses one employee token. Should a second
  token with `supervisor` role be added to the CI job so role-gated
  routes are exercised?
- The rate limiter uses an in-memory store. At what point does a
  Redis backend become necessary? Currently every app instance has
  its own counter, so N instances allow N × limit. S14.
- The `s6-authz-matrix.md` and `s3-tenant-audit.md` cover the same
  ground from different angles. Should they be merged?
