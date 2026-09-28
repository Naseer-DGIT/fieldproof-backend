# S5 Retrospective

- **Date:** 2026-09-24
- **Sprint:** S5

---

## What went well

1. **The crash-safe rekey pattern is simple and provable.** Three
   aliases, three fallback branches, three crash scenarios. Each
   branch has a test.
2. **The DR drill caught a real bug.** The restore script used the
   password from Secrets Manager instead of from `DATABASE_URL`. The
   drill exercised a real restore into a throwaway container and
   found it immediately.
3. **The classification check has teeth.** It caught a false positive
   on the first run. Fixing the pattern was faster than explaining
   why a `print` in the logger is fine.
4. **Secrets loading is one function.** `load_secrets(env)` is the
   only place that knows where secrets come from. Swapping the backend
   for tests is a one-line patch.

## What did not go well

1. **LocalStack `latest` requires an auth token.** Wasted an hour
   before switching to a mocked `boto3.client`. Should have checked
   the package's current licensing before adding it.
2. **`ALTER ROLE` does not accept bound parameters.** Discovered by
   running the drill, not by reading the docs. `psycopg.sql`
   composition is the fix.
3. **Stateless mocks hid a two-phase bug.** The DB rotation test
   passed against a mock that pretended `put_secret_value` did
   nothing. The fix was a stateful mock.
4. **`nosemgrep` id did not match the reported rule id.** The
   composed id (namespace.rule.rule) is what Semgrep expects, not the
   short form in the docs.
5. **Two commits landed on `develop` on mobile.** The branch fix
   required a force-push. The pre-commit branch guard
   (`scripts/check_branch.sh`) prevents this going forward.

## Action items for S6

| # | Action | Applied in |
|---|--------|-----------|
| 1 | Check package licensing before adding a dependency | S6 |
| 2 | Any two-phase operation ships with a stateful test | S6 |
| 3 | Read the composition docs for the driver before writing DDL | S6 |
| 4 | Run `scripts/check_branch.sh` before every commit | S6 |
| 5 | Semgrep `nosemgrep` uses the full composed id | S6 |
| 6 | Prefer real infra (drill, restore) over mocks for integration-shaped work | S6 |

## Questions to carry forward

- Should the JWT rotation force a client-side re-login, or should the
  client refresh silently? Current behavior is forced re-login.
- The `X-Forwarded-Proto` trust depends on the ALB stripping the
  header. Is there a way to test that assumption in S15?
- The mobile classification check uses grep. When the codebase grows,
  a real AST-based check (dart_code_metrics rule) would be more
  reliable. Worth doing before S10?
