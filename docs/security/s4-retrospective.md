# S4 Retrospective

- **Date:** 2026-09-23
- **Format:** individual, written
- **Sprint:** S4

---

## What went well

1. **The lab pattern worked.** Each day produced a self-contained
   artifact: a vulnerable module, a test, a fix, a report entry. The
   pattern is repeatable and could be reused for S20–S23 (AI security).

2. **The tests caught the skipped fixes.** On Days 2, 4, and 6 the fix
   was not applied. The tests failed immediately and precisely. That
   is the correct failure mode: the test is written to expect the fix,
   so a missing fix is loud.

3. **`s4-review.md` found the shared pattern.** Every vulnerability was
   an implicit decision, and every fix was an explicit check. Writing
   that down turned seven labs into one principle.

4. **Semgrep stayed clean on the fixed code.** The vulnerable versions
   would have been flagged; the fixed versions are not. That validates
   the fixes independently of the pytest suite.

## What did not go well

1. **The fix step was skipped three times (Days 2, 4, 6).** Each
   time, the test failure was misread as a test bug rather than a
   missing fix. The rule for S5: run the day's test file **before**
   staging any commit. If it fails, the fix is not applied.

2. **The mass assignment test had a fixture bug.** `_make_user()`
   returned `(email, user_id)` but the test unpacked it as
   `(email, tenant_id)`. The assertion `556 == 673` looked like a
   write succeeded when it had not. The fix: read state from the API,
   not from the fixture.

3. **The test count guard was dropped from `ci.yml`** during a rewrite
   between S3 and S4. Nobody noticed until Day 9. The fix: after
   editing a workflow, `grep` for the step names you expect.

4. **Several inline zsh mistakes.** `?` in a URL triggered glob
   expansion repeatedly. The fix: quote every URL passed to `curl`.

5. **`/tmp` scripts were cleared** by macOS between sessions. The fix:
   keep reusable helper scripts under `scripts/` in the repo.

## Action items for S5

| # | Action | Applied in |
|---|--------|-----------|
| 1 | Before `git add` on a lab day, run the day's test file and confirm it passes | S5 onward |
| 2 | Fixtures return minimal data; tests read state from the API | S5 |
| 3 | After editing `ci.yml`, grep for expected step names | S5 |
| 4 | Quote every URL passed to `curl` | S5 onward |
| 5 | Keep reusable scripts under `scripts/`, not `/tmp` | S5 |
| 6 | The lab pattern (module + test + fix + report) applies to AI security in S20–S23 | S20 |

## Questions to carry forward

- The lab modules are fixed but still present. Should they ship in the
  repo, or be deleted at S4 close? Keeping them is useful for
  interviews and for regression-testing the parser configurations.
- Should the seven rules in `s4-review.md` become a lint rule or a
  checklist item in the sprint template? A checklist is enough today;
  a lint rule is a later sprint's work.
- The mass assignment fix used `extra="forbid"`. Should every Pydantic
  input model set that globally? A shared base class would enforce it.
