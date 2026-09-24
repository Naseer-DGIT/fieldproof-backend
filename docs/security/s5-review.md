# S5 Security Review — Crypto, Secrets, Backups, Rekey

- **Date:** 2026-09-24
- **Sprint:** S5 (Day 8)
- **Reviewer:** Naseer
- **Scope:** TLS enforcement, secrets manager, key rotation, encrypted
  backups, DR drill, mobile rekey, classification check
- **Related:** ADR-0002, ADR-0004, DATA_CLASSIFICATION.md, threat_register.md

---

## Summary

- Files reviewed: 11
- Findings: 2 (both low, both with a plan)
- Accepted limitations: 4

---

## Findings

| # | File | Severity | Finding | Action |
|---|------|----------|---------|--------|
| F-1 | `scripts/backup_db.py` | Low | Passphrase passed via `--passphrase`, visible in `ps` | Move to `--passphrase-fd` (stdin) in S14 |
| F-2 | `scripts/restore_db.py` | Low | Same passphrase exposure as F-1 | Same fix |

Both are the same class of issue: a secret on a process command line.
Neither is exploitable on a solo developer machine or a single-user CI
runner. On a shared host it is. The fix is small and is scheduled for
S14 when the deployment story is real.

---

## Accepted limitations

1. **`X-Forwarded-Proto` is trusted unconditionally.** The redirect
   middleware assumes the request came through the ALB. If the app is
   reachable directly, an attacker can suppress the redirect. The
   deployment in S15 places the app in a private subnet behind the ALB,
   and the ALB strips the header from inbound requests. Until then, this
   is a deployment concern, not a code defect.

2. **`lru_cache` on `load_secrets` means rotation takes effect on
   restart.** Documented in ADR-0004. Acceptable for `JWT_SECRET` and
   the DB password, both of which are long-lived.

3. **The classification check is a static grep, not a proof.** It
   catches interpolation and map keys. It does not catch a value passed
   through a renamed variable. Runtime redaction in `SecureLogger`
   covers the common case; the rest is review.

4. **The mobile rekey runs on the main isolate.** A large queue could
   block the UI during the rekey. Documented in
   `s5-mobile-rekey.md`. Moving to a background isolate is S14 work.

---

## Per-file review

### security_headers.py
- Redirect gated on `force_https`: yes
- `/health` exempt: yes
- `X-Forwarded-Proto` honored: yes (accepted limitation 1)
- HSTS sent only when enabled: yes
- Verdict: PASS

### secrets.py
- Dev/lab use env with safe defaults: yes
- Staging/prod require a real secret: yes
- Errors name the missing field, not the value: yes
- Verdict: PASS

### rotate_jwt_secret.py
- Dry run writes nothing: yes
- Other fields preserved: yes
- No secret in output: yes
- Verdict: PASS

### rotate_db_password.py
- `--prepare` does not touch the DB: yes
- `--commit` uses `psycopg.sql`: yes
- DB updated before secret written: yes (correct order)
- Verdict: PASS

### backup_db.py
- Encrypted with AES-256: yes
- SHA sidecar written: yes
- Passphrase on command line: yes (finding F-1)
- Verdict: PASS with finding

### restore_db.py
- Hash verified before decrypt: yes
- Unsafe target refused: yes
- Passphrase on command line: yes (finding F-2)
- Verdict: PASS with finding

### dr_drill.py
- Cleanup on success and failure: yes
- Refuses to run with leftover container: yes
- Reads source DB, never writes: yes
- Verdict: PASS

### database.dart (mobile)
- Open tries primary, next, prev: yes
- Promotes on next success: yes
- Demotes on prev success: yes
- Throws when all fail: yes
- Verdict: PASS

### key_store.dart
- Three aliases distinct: yes
- `wipe()` clears everything: yes
- No key value logged: yes
- Verdict: PASS

### rekey_policy.dart
- 90-day interval: yes
- First-run timestamp: yes
- Failure logged, not fatal: yes
- Verdict: PASS

### check_classification.sh
- Allows the logger's own print: yes
- Distinguishes messages from data: yes
- Denylist count guard: yes
- Verdict: PASS

---

## Sweep results

| Check | Result |
|-------|--------|
| Backend full suite | 62 passed, 25 skipped |
| Backend semgrep | clean |
| Mobile analyze | no issues |
| Mobile full suite | 35 passed |
| Classification check | passed |
| No passphrase literal in scripts | clean |
| Three DB key aliases present | yes |
| Rekey preserves data | yes (integration test) |

---

## Conclusion

S5 delivers TLS enforcement, secrets management, rotation, encrypted
backups, a DR drill, and a crash-safe mobile rekey. Two low-severity
findings are documented with a plan for S14. Four accepted limitations
are known and documented. No blocking findings.
