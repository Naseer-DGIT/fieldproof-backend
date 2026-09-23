# S4 — AppSec Lab: Sprint Summary

- **Sprint:** S4 (Days 1–10)
- **Branch:** `sprint/s4-appsec`
- **Dates:** 2026-09-18 → 2026-09-23
- **Author:** Naseer
- **Related:** `docs/security/s4-appsec-lab.md`, `docs/security/s4-review.md`, `threat_register.md`

---

## Goal

Build seven deliberate vulnerabilities in an isolated `app/lab/`
package, each with a proof-of-concept test, a fix, and a written
report. The final state of every module is fixed.

---

## Deliverables

| Day | Lab | Class | OWASP | Commit |
|-----|-----|-------|-------|--------|
| 1 | SQL injection | CWE-89 | A03 | `523acfd` |
| 2 | BOLA | CWE-639 | API1 | `81c60d6` |
| 3 | XXE | CWE-611 | A05 | `f78eb36` |
| 4 | Insecure deserialization (pickle) | CWE-502 | A08 | `054275a` |
| 5 | SSRF | CWE-918 | API7 | `d53a073` |
| 6 | Mass assignment | CWE-915 | API3 | `a5caf72` |
| 7 | Path traversal | CWE-22 | A01 | `0c3dc89` |
| 8 | Security review | — | — | `0ec410e` |
| 9 | CI verification | — | — | `d2e6f30` |
| 10 | Summary, retrospective, PR, tag | — | — | *(this PR)* |

---

## What was built

### Lab package (`app/lab/`)

- Seven modules, each with a deliberately vulnerable version, a
  documented fix, and a test that proves both states.
- Mounted only when `ENVIRONMENT=lab`. No production module imports
  from `app.lab`.
- Each module has a top-level docstring stating it is intentionally
  vulnerable and explaining the fix.

### Test suite

- 19 lab tests under `tests/lab/`.
- Guarded by `RUN_LAB_TESTS=1`. Not run in CI.
- Each test proves the vulnerability before the fix and the fix after.

### Report

- `docs/security/s4-appsec-lab.md` — one section per lab: root cause,
  exploit, impact, fix, verification.
- `docs/security/s4-review.md` — the cross-cutting analysis: rules for
  production code, recurring patterns, and what S4 did not cover.

---

## Verification

- Lab tests: 19 passed (`RUN_LAB_TESTS=1 pytest tests/lab/ -v`)
- Non-lab suite: passes on every push
- Semgrep on `app/` and `app/lab/`: 0 findings
- CI green on `sprint/s4-appsec`
- No production module imports `app.lab`
- `main.py` guards the lab mount with `if _settings.is_lab:`

---

## Rules extracted

Each lab produced one rule for production code:

1. **SQL injection** — bind values, never interpolate.
2. **BOLA** — resolve by id AND owner in a single query.
3. **XXE** — deny by default in parsers.
4. **Pickle** — never deserialize untrusted input with pickle.
5. **SSRF** — validate outbound URLs by resolved IP.
6. **Mass assignment** — write endpoints have an allowlist.
7. **Path traversal** — resolve filesystem paths and confirm the base.

Three cross-cutting patterns:

- Whitelist beats blacklist.
- Single source of truth for the check.
- Reject, do not silently ignore.

---

## Findings resolved during the sprint

| # | Finding | Resolution |
|---|---------|-----------|
| F-1 | BOLA fix skipped, test failed on Day 2 | Fix applied; commit reissued |
| F-2 | Pickle fix skipped, test failed on Day 4 | Fix applied; commit reissued |
| F-3 | Mass assignment fix skipped, test failed on Day 6 | Fix applied; commit reissued |
| F-4 | `_make_user()` in the mass assignment test returned `(email, user_id)` but was unpacked as `(email, tenant_id)` | Fixture simplified to return only email; state read from `/auth/me` |
| F-5 | Test count guard was dropped from `ci.yml` during an earlier rewrite | Guard restored with floor 58 |
| F-6 | Semgrep step name said "non-blocking in S3" but semgrep is blocking | Step renamed |

---

## Accepted limitations

1. **Lab tests do not run in CI.** They require `ENVIRONMENT=lab` and
   `RUN_LAB_TESTS=1`, and they exercise deliberately vulnerable code.
   Running them in CI would make the product's merge gate depend on
   code that is not part of the product.

2. **`app/lab/__init__.py` docstring still says "Deliberately
   vulnerable code".** That is a warning, not a vulnerability marker.
   The phrase "Deliberately vulnerable" appears only there; no lab
   module contains it.

3. **Coverage gaps not addressed in S4:** CSRF, race conditions,
   business logic flaws, SSTI, and prompt injection. Listed in
   `s4-review.md`.

---

## Metrics

- Commits on the sprint branch: 12
- Lab tests: 19
- Lab modules: 7
- Lines in the report: ~350
- Rules extracted: 7 production rules + 3 cross-cutting patterns
- Production code affected: 0

---

## Explicitly out of scope (moved to later sprints)

- TLS, KMS, backup/DR (S5)
- API pentest with Burp and ZAP (S6)
- Analytics and reports (S7)
- Mobile MASVS/MASTG (S8)
- MobSF (S9)
- Frida runtime testing (S10)
- Certificate pinning (S11)
- SBOM, signing, supply chain (S12–S14)
- Cloud/IaC (S15)
- Kubernetes (S18–S19)
- AI security labs (S20–S23)
