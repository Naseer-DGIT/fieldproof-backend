# S7 — Workforce Analytics: Sprint Summary

- **Sprint:** S7 (Days 1–10)
- **Branch:** `sprint/s7-analytics`
- **Dates:** 2026-09-28 → 2026-09-30
- **Author:** Naseer
- **Related:** ADR-0002, ADR-0003, threat_register.md

---

## Goal

Deliver the workforce analytics layer: shifts, leave, LOP, per-user and
tenant-wide aggregates, and report endpoints with CSV export. Every
endpoint is role-gated and tenant-scoped; every new route is documented
in the audit tables.

---

## Deliverables

| Day | Deliverable |
|-----|-------------|
| 1 | Shift and leave models, tenant helpers |
| 2 | Shift API, assignment endpoints, policy classifier |
| 3 | Leave types, requests, approval flow |
| 4 | LOP computation service and endpoint |
| 5 | Analytics aggregations — hours, breaks, punctuality, overtime |
| 6 | Tenant-wide analytics — rollup, per-shift, per-team |
| 7 | Report endpoints and CSV export |
| 8 | Security review |
| 9 | CI verification, test count floor raised |
| 10 | Summary, retrospective, PR, tag |

---

## What was built

### Models (Day 1)

Five new tables, all `tenant_id NOT NULL` with `ondelete="CASCADE"`:

- `shifts`
- `shift_assignments`
- `leave_types`
- `leave_requests`
- `lop_records`

### Shift management (Day 2)

- `POST /shifts` — create a shift (hr_ops+)
- `GET /shifts` — list tenant shifts
- `POST /shifts/assignments` — assign a shift (supervisor+)
- `GET /shifts/assignments` — list assignments, employees self-only
- `app/services/shift_policy.py` — classifies a day as `on_time`,
  `late`, `early_leave`, `absent`, `on_leave`, or `no_shift`

### Leave management (Day 3)

- `POST /leave/types`, `GET /leave/types`
- `POST /leave/requests`, `GET /leave/requests`
- `POST /leave/requests/{id}/decision` (supervisor+)
- `POST /leave/requests/{id}/cancel`
- `app/services/leave.py` — overlap check, past-date check, role checks

### LOP (Day 4)

- `POST /lop/compute` — idempotent computation over a date range
- `GET /lop` — list tenant LOP records
- Sources: `unapproved_absence` (1.0 day), `late_arrival` (0.5),
  `insufficient_hours` (0.5). Manual rows preserved.

### Analytics (Days 5–6)

- `GET /analytics/me` — caller's day summaries
- `GET /analytics/users/{id}` — supervisor/HR view of another user
- `GET /analytics/tenant` — tenant rollup
- `GET /analytics/by-shift`
- `GET /analytics/by-team`

Per day: scheduled minutes, worked minutes, break analysis, punctuality,
overtime. Tenant rollup includes `attendance_rate`.

### Reports (Day 7)

- `GET /reports/attendance-summary`
- `GET /reports/work-hours`
- `GET /reports/breaks`
- `GET /reports/lop`
- `format=json` (default) or `format=csv` (streamed)

### Cross-cutting

- Every endpoint is documented in `s3-tenant-audit.md` and
  `s6-authz-matrix.md`
- The hygiene test fails if a route is added without an audit row
- Range is capped at 62 days on every report and analytics endpoint

---

## Verification

- `pytest -q` → 143 passed, 26 skipped
- `semgrep app/ scripts/` → 0 findings
- Hygiene test green
- CI green on `sprint/s7-analytics`

---

## Findings resolved during the sprint

| # | Finding | Resolution |
|---|---------|-----------|
| F-1 | Policy tests created users in different tenants | Fixture uses a shared tenant |
| F-2 | Test events missing required `event_id` | Added to all three inserts |
| F-3 | `by_team` unassigned test off by one | Test includes the HR user |
| F-4 | Audit rows not inserted due to substring match bug | Full-line presence check |
| F-5 | Test count floor patch did not apply | Quoted heredoc, hardcoded floor |

---

## Accepted limitations

1. **Wall-clock times are UTC.** A tenant timezone column is V1.5.
2. **Analytics compute is per-user per-day.** Batching is S14.
3. **CSV injection not sanitized.** No user-controlled text columns
   today. When one is added, prefix a single quote.
4. **`team_id` is a plain integer.** A Team model is deferred.
5. **Per-site and per-department breakdowns deferred.** No Site or
   Department model exists.
6. **No scheduled reports.** On-demand only.

---

## Explicitly out of scope (moved to later sprints)

- Mobile MASVS/MASTG (S8)
- MobSF (S9)
- Frida runtime testing (S10)
- Certificate pinning (S11)
- CI/CD supply chain (S12–S14)
- Cloud/IaC (S15)
- Kubernetes (S18–S19)
- AI analytics (S20+)

---

## Threats closed or verified

From `threat_register.md`:

| ID | Threat | S7 coverage |
|----|--------|-------------|
| T-006 | BOLA | Extended to shift, leave, LOP, analytics, report routes |
| T-007 | Cross-tenant read | Every helper and endpoint verified |
| T-008 | BFLA | Every privileged route role-gated |

---

## Metrics

- Commits on the sprint branch: 18
- Tests: 143 passed, 26 skipped
- New tables: 5
- New endpoints: 19
- New services: 4 (`shift_policy`, `leave`, `lop`, `analytics`, `reports`)
- Accepted limitations: 6
