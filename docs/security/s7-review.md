# S7 Security Review — Workforce Analytics

- **Date:** 2026-09-30
- **Sprint:** S7 (Day 8)
- **Reviewer:** Naseer
- **Scope:** shift, leave, LOP, analytics, report endpoints and their services
- **Related:** threat_register.md, ADR-0003, `docs/security/s3-tenant-audit.md`

---

## Summary

- Files reviewed: 13
- Findings: 0
- Accepted limitations: 6

---

## Findings

No blocking findings. All S7 artifacts meet the sprint's scope.

---

## Accepted limitations

1. **Wall-clock times are UTC.** Shift start and end times are stored as
   local wall-clock strings and treated as UTC by the policy and
   analytics services. A tenant timezone column is a V1.5 concern.
   Documented in `shift_policy.py`.
2. **Analytics compute is per-user per-day.** For a tenant with N users
   and D days, the report path runs N × D `summary_for_range` calls.
   At the 62-day cap and a few hundred users, the query volume is
   manageable. Batching is S14.
3. **CSV injection not sanitized.** Excel executes cells beginning with
   `=`, `+`, `-`, or `@`. None of the current report columns are
   user-controlled text, so there is no exploit path. When a
   user-supplied text column is added, prefix a single quote.
4. **`team_id` is a plain integer.** No Team model exists. The
   `by_team` aggregation groups on the integer. A future Team model
   will need a migration and a join.
5. **Per-site and per-department breakdowns are deferred.** No Site or
   Department model exists. The S7 plan mentioned them; they are
   postponed to a sprint where those models land.
6. **No scheduled reports.** Report generation is on-demand. A
   scheduler for monthly reports is V1.5.

---

## Per-file review

### app/models.py (S7 tables)
- `tenant_id NOT NULL` on every new table: yes
- `ondelete="CASCADE"` from tenants: yes
- Unique constraints correct: yes
- Verdict: PASS

### app/core/tenant.py (S7 helpers)
- Every helper takes a `User`: yes
- Filters on `user.tenant_id`: yes
- Function-local imports avoid cycles: yes
- Verdict: PASS

### app/services/shift_policy.py
- Wall-clock assumption documented: yes
- Handles `no_shift`: yes
- Approved leave short-circuits: yes
- Classification deterministic: yes
- Verdict: PASS

### app/api/shifts.py
- Role gating on create and assign: yes
- Shift lookup tenant-scoped: yes
- User lookup tenant-scoped: yes
- Overlap check tenant-scoped: yes
- Employee sees own assignments only: yes
- Verdict: PASS

### app/api/leave.py
- Request creation cannot target another user: yes
- Leave type lookup tenant-scoped: yes
- Decision resolves request in tenant: yes
- `can_decide` rejects employees: yes
- `can_cancel` restricts employees to own pending: yes
- Verdict: PASS

### app/services/lop.py
- Idempotent via unique constraint: yes
- Manual rows preserved: yes (source `manual` is not touched)
- Range checked upstream: yes
- Verdict: PASS

### app/api/lop.py
- Compute is hr_ops/sys_admin: yes
- List is hr_ops/sys_admin: yes
- Range capped at 62 days: yes
- Verdict: PASS

### app/services/analytics.py
- `summary_for_range` filters by user: yes (caller passes the user)
- `tenant_rollup` counts only users in the tenant: yes
- `by_team` includes null bucket: yes
- No cross-tenant leakage path: yes
- Verdict: PASS

### app/api/analytics.py
- `/me` returns caller only: yes
- `/users/{id}` checks tenant: yes
- Supervisors restricted to own team: yes
- `/tenant`, `/by-shift`, `/by-team` role-gated: yes
- Verdict: PASS

### app/services/reports.py
- Every generator uses tenant-scoped source: yes
- Memory bounded by 62-day cap: yes
- Verdict: PASS

### app/api/reports.py
- All four endpoints are `require_role(hr_ops, security_admin, sys_admin)`: yes
- Range capped: yes
- `format` regex rejects unknown: yes
- Verdict: PASS

### app/core/csv_stream.py
- Empty list handled: yes
- Header from first row: yes
- `csv.writer` quoting: yes
- Injection limitation documented: yes
- Verdict: PASS

### Audit docs
- All routes in `s3-tenant-audit.md`: yes (hygiene test)
- All routes in `s6-authz-matrix.md`: yes
- Verdict: PASS

---

## Sweep results

| Check | Result |
|-------|--------|
| Full suite | 143 passed, 26 skipped |
| Semgrep app/ scripts/ | 0 findings |
| Hygiene test | passed |
| Range caps in reports/analytics/LOP | present |
| CSV streamed | yes |
| No secret literal in S7 files | clean |

---

## Threats closed or verified

From `threat_register.md`:

| ID | Threat | S7 coverage |
|----|--------|-------------|
| T-006 | BOLA | Extended to shift, leave, LOP, analytics, report routes |
| T-007 | Cross-tenant read | Every helper and endpoint verified |
| T-008 | BFLA | Every privileged route role-gated |

---

## Conclusion

S7 delivers the workforce analytics layer: shift and leave models,
LOP computation, per-user and tenant-wide aggregates, and report
endpoints with CSV export. The full suite passes, hygiene is green,
semgrep is clean. Six accepted limitations are documented, all with a
plan or a rationale. No blocking findings.
