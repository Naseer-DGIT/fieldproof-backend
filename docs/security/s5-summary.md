# S5 — Crypto & Data: Sprint Summary

- **Sprint:** S5 (Days 1–10)
- **Branch:** `sprint/s5-crypto`
- **Dates:** 2026-09-24 → 2026-09-24
- **Author:** Naseer
- **Related:** ADR-0002, ADR-0004, DATA_CLASSIFICATION.md, threat_register.md

---

## Goal

Deliver the crypto and data-protection layer: TLS enforcement, secrets
management, key rotation, encrypted backups, disaster recovery, mobile
SQLCipher rekey, and static classification enforcement.

---

## Deliverables

| Day | Deliverable | Commit |
|-----|-------------|--------|
| 1 | Conditional HTTPS redirect and HSTS for staging/prod | `40a5f6d`, `6f4ed62` |
| 2 | Secrets manager — env backend, AWS Secrets Manager for staging/prod | `c705ef0` |
| 3 | Key rotation policy (ADR-0004) and rotation scripts | `27ac4a5` |
| 4 | Encrypted backups — pg_dump + GPG AES-256 | `1a05728`, `505a795` |
| 5 | Disaster recovery runbook and drill script | `5115dd0` |
| 6 | (mobile) SQLCipher rekey — crash-safe two-phase rotation | `2d2b41d` |
| 7 | (mobile) Data classification enforcement in CI | `59d93f1` |
| 8 | Security review | `b57c0a0` |
| 9 | Test count floor raised, semgrep scans scripts/ | `114a01b` |
| 10 | Summary, retrospective, PR, tag | *(this PR)* |

---

## What was built

### TLS

- `HttpsRedirectMiddleware` and `HstsHeaderMiddleware` in
  `app/core/security_headers.py`
- Conditional on `settings.force_https` and `settings.hsts_enabled`
- Both derived from `ENVIRONMENT`: true for staging/prod, false for
  dev/lab
- `/health` exempt from redirect
- `X-Forwarded-Proto` respected for proxy deployments

### Secrets

- `app/core/secrets.py::load_secrets(environment)`
- Dev/lab read from env with safe defaults
- Staging/prod read from AWS Secrets Manager
- One JSON secret per env: `fieldproof/{env}/app` with
  `jwt_secret`, `database_password`, `backup_passphrase`
- `lru_cache` per process

### Rotation

- ADR-0004: 90-day interval for JWT secret and DB password
- `scripts/rotate_jwt_secret.py` with `--dry-run`
- `scripts/rotate_db_password.py` with `--prepare` and `--commit`
- `ALTER ROLE` uses `psycopg.sql` composition

### Backups

- `scripts/backup_db.py` — GPG symmetric AES-256, SHA-256 sidecar
- `scripts/restore_db.py` — hash verify, target-name guard
- Round-trip test on a small source DB

### Disaster recovery

- `docs/security/s5-disaster-recovery.md` — runbook
- `scripts/dr_drill.py` — five-phase drill against a throwaway container
- Opt-in test via `RUN_DR_DRILL_TEST=1`

### Mobile rekey

- Three-alias scheme: `primary`, `next`, `prev`
- `AppDatabase._open` tries each in order
- `AppDatabase.rekey()` runs the five-phase crash-safe rotation
- `RekeyPolicy` enforces the 90-day interval
- VM tests for policy, integration tests for the DB operation

### Classification

- `scripts/check_classification.sh` in mobile CI
- Fails on `print`/`debugPrint` outside the logger
- Fails on forbidden identifiers in dangerous positions
- Fails on `shared_preferences` in `lib/`

---

## Verification

Backend:
- `pytest -q` → 68 passed, 19 skipped (with opt-ins)
- `semgrep --config=p/owasp-top-ten app/ scripts/` → 0 findings
- CI green on `sprint/s5-crypto`

Mobile:
- `flutter analyze` → No issues found
- `flutter test` → all pass
- Classification check → passed
- CI green on `sprint/s5-crypto`

---

## Findings resolved during the sprint

| # | Finding | Resolution |
|---|---------|-----------|
| F-1 | `psycopg2` had no wheels for Python 3.14 (S0) | `psycopg[binary]` |
| F-2 | `bcrypt` 4.2 incompatible with `passlib` 1.7.4 | Pin to `bcrypt==4.0.1` |
| F-3 | LocalStack `latest` tag requires an auth token | Switched secrets tests to a mocked `boto3.client` |
| F-4 | `ALTER ROLE` rejected bound parameters | `psycopg.sql` composition |
| F-5 | Stateless mock hid two-phase rotation bugs | Stateful mock with `side_effect` |
| F-6 | Classification check flagged the logger's own `print` | Path allowlist |
| F-7 | Substring match flagged event names as data | Refined to interpolation and map keys |
| F-8 | `nosemgrep` id did not match the reported rule id | Full composed id |

---

## Accepted limitations

1. **`X-Forwarded-Proto` is trusted unconditionally.** Deployment in
   S15 places the app behind an ALB that strips the header.
2. **`lru_cache` on `load_secrets`.** Rotation takes effect on restart.
3. **Passphrase on the `gpg` command line.** Visible in `ps`. Fix in S14.
4. **Classification check is a static grep, not a proof.** A value
   passed through a renamed variable is not caught.

---

## Explicitly out of scope (moved to later sprints)

- OWASP API pentest (S6)
- Analytics and reports (S7)
- Mobile MASVS/MASTG (S8)
- MobSF (S9)
- Frida runtime testing (S10)
- Certificate pinning (S11)
- CI/CD supply chain — SBOM, signing (S12–S14)
- Cloud/IaC (S15)

---

## Metrics

- Commits on the sprint branch: 12 (backend)
- Backend tests: 68 passed, 19 skipped
- Backend test files: 12
- Mobile tests: all passing
- ADRs referenced: 2 (ADR-0002, ADR-0004)
- Threat register entries closed or mitigated: T-002 (transport),
  T-011 (local DB tampering, rekey)
