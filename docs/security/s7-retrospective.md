# S7 Retrospective

- **Date:** 2026-09-30
- **Sprint:** S7

---

## What went well

1. **The policy module was small and testable.** `classify_day` is a
   pure function over events and a shift. Every status has a test.
2. **The helpers from S3 carried forward.** Every new endpoint uses a
   helper from `tenant.py`. No raw `db.query()` in a router.
3. **The hygiene test caught every missing audit row.** Five times
   across the sprint. That is the intended friction.
4. **The report CSV path streams.** No memory concern even for large
   tenants.
5. **The LOP computation is idempotent via the unique constraint.**
   Rerunning over the same range updates rather than duplicates.

## What did not go well

1. **The audit-row insertion kept failing.** Twice the Python check
   used a substring (`"POST"`, `/me`) as the presence test and skipped
   the insert. The fix was exact-line matching.
2. **The test count floor patch was silent.** The heredoc was
   unquoted, so `$FLOOR` expanded to empty before Python saw it.
3. **The policy tests created users in different tenants.** HR and
   employee ended up in separate tenants, so the assignment was
   invisible to the lookup.
4. **The test file was committed empty once.** The heredoc was
   truncated before the closing `EOF`. `wc -l` would have caught it.
5. **The tag ordering was wrong on Day 9.** `s7-day9` was created
   before the workflow change was committed.

## Action items for S8

| # | Action | Applied in |
|---|--------|-----------|
| 1 | Use exact-line presence checks when inserting into docs | S8 |
| 2 | Always use quoted heredoc delimiters (`<<'EOF'`) | S8 |
| 3 | Run `wc -l` after every `cat >` heredoc | S8 |
| 4 | Verify staged files with the strict check before commit | S8 |
| 5 | Test fixtures for multi-user scenarios must share a tenant | S8 |
| 6 | Tag only after `git status --porcelain` is empty | S8 |

## Questions to carry forward

- When Site and Department models land, do the analytics
  aggregations move to a single SQL `GROUP BY`, or stay in Python
  iterating per user? At scale, SQL wins; the current shape is fine
  up to a few hundred users.
- The 62-day range cap is arbitrary. Should it be a config value?
- The `by_team` endpoint returns a `null` bucket for unassigned
  users. Should the HR dashboard display this as "Unassigned" or
  hide it?
- CSV injection is a latent issue. Before any user-supplied text
  column is added to a report, the writer needs a prefix rule.
- Reports are computed on demand. A tenant with 500 users and a
  62-day range triggers ~31,000 `summary_for_range` calls. A
  pre-aggregated table would change the cost shape entirely.
