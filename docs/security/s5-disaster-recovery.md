# S5 — Disaster Recovery Runbook

- **Date:** 2026-09-24
- **Sprint:** S5 (Day 5)
- **Author:** Naseer
- **Related:** ADR-0004, `docs/security/s5-backups.md`

---

## Scope

This runbook covers loss of the PostgreSQL database. It does not cover:

- Loss of the Secrets Manager entry (AWS account recovery)
- Loss of the backup passphrase (backups become unreadable)
- Loss of the entire AWS region (S15 concern)

---

## Scenarios

| Scenario | Recovery target | Tool |
|----------|-----------------|------|
| Table dropped by mistake | Minutes | Restore latest backup into prod |
| DB volume corrupted | 30 minutes | Restore latest backup into prod |
| DB container deleted | 30 minutes | Recreate container, restore backup |
| Full region loss | Hours | Rebuild from S3 copy in another region |

RPO (how much data you can afford to lose): the interval between
backups. In dev, manual. In staging and prod, a nightly job (S14).
Target RPO is 24 hours.

RTO (how long recovery takes): the time from "we know it is gone" to
"the app is serving traffic again". Target RTO is 1 hour for prod.

---

## Preconditions

- Access to the backup directory (S3 in staging and prod)
- `BACKUP_PASSPHRASE` from Secrets Manager
- `pg_dump` and `psql` on the machine running the recovery
- The Postgres container or instance reachable

Verify:

```bash
aws secretsmanager get-secret-value \
  --secret-id fieldproof/prod/app \
  --query SecretString --output text | jq .backup_passphrase
