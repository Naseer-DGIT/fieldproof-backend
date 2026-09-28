# S6 Security Review — API Testing

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 8)
- **Reviewer:** Naseer
- **Scope:** security headers, rate limiting, ZAP scans, manual pentest,
  authorization matrix, attack tree, CI integration
- **Related:** threat_register.md, ADR-0003, `docs/security/s3-tenant-audit.md`

---

## Summary

- Files reviewed: 11
- Findings: 0
- Accepted limitations: 5

---

## Findings

No blocking findings. All S6 artifacts meet the sprint's scope.

---

## Accepted limitations

1. **Rate limits are per-process.** A rolling restart resets the
   counter. Redis-backed storage is S14.
2. **Rate limits key on `request.client.host`.** Behind a proxy this
   is the proxy address unless the proxy is configured to preserve the
   client IP at the TCP level. `X-Forwarded-For` handling is S15.
3. **IPv6 and IPv4 localhost are different keys.** Local-only; not a
   bypass on a real network.
4. **The ZAP authenticated scan uses an employee token.** Supervisor
   and admin routes are not exercised by ZAP. The Day 3 manual tests
   cover BOLA and BFLA.
5. **The ZAP authenticated scan does not test signed payloads.**
   `/attendance/events` POST requires an Ed25519 signature that ZAP
   cannot produce. The Day 3 manual test covers this path.

---

## Per-file review

### app/core/security_headers.py
- Baseline headers always on: yes
- CSP correct for JSON API: yes (`default-src 'none'`)
- Middleware order correct: yes (added first, runs innermost)
- Headers present on error responses: yes
- Verdict: PASS

### app/core/limiter.py
- Limits environment-derived: yes
- Staging/prod limits realistic: yes (10/min login, 60/min events)
- Key function is `get_remote_address`: yes
- `X-Forwarded-For` ignored: yes (verified in Day 7 Test 3)
- Verdict: PASS

### app/api/auth.py
- Limit decorator applied: yes
- Decorator order correct (below route): yes
- Verdict: PASS

### app/api/attendance.py
- Limit decorator applied: yes
- Limit value environment-derived: yes
- Verdict: PASS

### docs/security/s6-zap-baseline.md
- All findings dispositioned: yes
- Fix commit referenced: yes (Day 2)
- Verdict: PASS

### docs/security/s6-zap-authenticated.md
- Token injection documented: yes
- Role limitation noted: yes
- Coverage claims honest: yes
- Verdict: PASS

### docs/security/s6-burp.md
- Six tests documented: yes
- Actual outputs recorded: yes
- Open leaves documented: yes
- Verdict: PASS

### docs/security/s6-authz-matrix.md
- Every route in the code appears: yes
- Enforcement named per row: yes
- Lab routes marked: yes
- Verdict: PASS

### docs/security/s6-attack-tree.md
- Every leaf marked: yes
- Every open leaf has a mitigation or accepted limitation: yes
- Verdict: PASS

### docs/security/s6-rate-limit-load.md
- All bypass attempts documented: yes
- IPv6/IPv4 noted: yes
- Redis limitation noted: yes
- Verdict: PASS

### .github/workflows/ci.yml
- zap-api on label or schedule: yes
- Backend started before ZAP: yes
- Fails on high-risk alerts: yes
- Report uploaded: yes
- Verdict: PASS

---

## Sweep results

| Check | Result |
|-------|--------|
| Full suite | <PASTE> |
| Semgrep app/ scripts/ | 0 findings |
| No `print` outside lab | clean |
| No hardcoded secret | clean |
| Rate limits env-derived | login 1000/min (dev), events 1000/min (dev) |
| SecurityHeadersMiddleware registered | yes |
| Lab routes gated | yes |
| Hygiene test | passed |

---

## Threats closed or verified

From `threat_register.md`:

| ID | Threat | S6 coverage |
|----|--------|-------------|
| T-001 | Credential stuffing | Rate limit + Day 7 load test |
| T-004 | Replay of old event | Day 3 Test 3 |
| T-006 | BOLA | Day 3 Test 1 |
| T-007 | Cross-tenant read | Day 3 Test 1 + pytest suite |
| T-008 | BFLA | Day 3 Test 2 |
| T-010 | Flood sync | Rate limit + Day 7 |

---

## Conclusion

S6 delivers the API security testing phase: baseline scan, header and
rate-limit fixes, six manual pentest tests (all pass), an authenticated
ZAP scan, an authorization matrix, an attack tree for the highest-value
endpoint, a rate-limit load test, and CI integration. No blocking
findings. Five accepted limitations documented.
