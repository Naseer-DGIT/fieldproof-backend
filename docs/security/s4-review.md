# S4 Security Review — AppSec Lab

- **Date:** 2026-09-23
- **Sprint:** S4 (Day 8)
- **Reviewer:** Naseer
- **Scope:** `app/lab/` — seven deliberate vulnerabilities, each with a
  proof, a fix, and a test that proves both states
- **Related:** `docs/security/s4-appsec-lab.md`, `threat_register.md`,
  `DATA_CLASSIFICATION.md`

---

## Summary

| # | Lab | Class | OWASP | Status |
|---|-----|-------|-------|--------|
| 1 | SQL injection | CWE-89 | A03 Injection | Fixed |
| 2 | BOLA | CWE-639 | API1 BOLA | Fixed |
| 3 | XXE | CWE-611 | A05 Misconfiguration | Fixed |
| 4 | Insecure deserialization | CWE-502 | A08 Integrity | Fixed |
| 5 | SSRF | CWE-918 | API7 SSRF | Fixed |
| 6 | Mass assignment | CWE-915 | API3 Property Authz | Fixed |
| 7 | Path traversal | CWE-22 | A01 Access Control | Fixed |

- Lab tests: 19 passing
- Fixes applied: 7 of 7
- Reports written: 7 of 7 in `s4-appsec-lab.md`
- Production code affected: none — all labs are in `app/lab/`

---

## What the seven labs have in common

Reading them in sequence, one pattern appears: **the vulnerability is
almost always a decision the code made implicitly.** The fix is to
make that decision explicit and to verify it.

| Lab | Implicit decision | Explicit fix |
|-----|-------------------|--------------|
| SQLi | "The query string is data" | The value is a bound parameter; the SQL string is constant |
| BOLA | "The id is enough to find the resource" | The query filters on id **and** owner |
| XXE | "The parser handles entities" | The parser is told not to |
| pickle | "These bytes are data" | The format cannot construct objects, so it is safe |
| SSRF | "The URL is a destination" | The URL resolves to a checked IP |
| Mass assignment | "The client sends what it owns" | Only allowlisted fields are copied |
| Path traversal | "The base directory anchors the path" | Both sides resolve; the result is checked |

Every fix took the shape: **name the assumption, then verify it.**

---

## Rules for production code

### 1. Bind values, never interpolate

```python
# wrong
text(f"SELECT ... WHERE email = '{q}'")

# right
text("SELECT ... WHERE email = :email").bindparams(email=q)
# wrong — fetches any row, then checks
event = db.get(AttendanceEvent, id)
if event.user_id != user.id: raise

# right — the filter is the query
event = (
    db.query(AttendanceEvent)
    .filter_by(event_id=id, user_id=user.id)
    .first()
)

---

## Day 9 — CI verification

- Workflow: `.github/workflows/ci.yml`
- Trigger: every push to `sprint/s4-appsec`
- Latest run: success
- Semgrep on `app/lab/`: 152 rules, 8 files, 0 findings
- Collected test count: 58 (lab tests collected but skipped in CI)
- Test count guard: floor 58
- Lab tests: not run in CI. They require `ENVIRONMENT=lab` and
  `RUN_LAB_TESTS=1`, and they exercise deliberately vulnerable code.
- Production surface: no production module imports from `app.lab`.
  The lab router is mounted only when `settings.is_lab` is true.

### Decision — lab tests do not gate CI

Running the lab tests in CI would require:
- Starting the server with `ENVIRONMENT=lab`
- Setting `RUN_LAB_TESTS=1`
- Accepting that a regression in a lab module (not part of the
  product) would block a production merge

None of those trade-offs are worth it in S4. If lab tests are ever
wanted in CI, they get their own job with its own trigger, not the
production gate.
