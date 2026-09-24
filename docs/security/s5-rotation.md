# S5 — Key Rotation Procedure

- **Date:** 2026-09-24
- **Sprint:** S5 (Day 3)
- **Author:** Naseer
- **Related:** ADR-0004

---

## Summary

| Secret | Interval | Script | Downtime |
|--------|----------|--------|----------|
| JWT_SECRET | 90 days | `scripts/rotate_jwt_secret.py` | none |
| DB password | 90 days | `scripts/rotate_db_password.py` | brief restart |
| SQLCipher key (mobile) | on revoke | mobile rekey (S5 Day 6) | none |

---

## JWT secret rotation

```bash
# 1. Dry run to confirm the secret is readable
python scripts/rotate_jwt_secret.py --environment staging --dry-run

# 2. Rotate
python scripts/rotate_jwt_secret.py --environment staging

# 3. Restart the app for the new secret to take effect
