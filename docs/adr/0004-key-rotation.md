# ADR-0004: Key and Secret Rotation

- **Status:** Accepted
- **Date:** 2026-09-24
- **Sprint:** S5 (Day 3)
- **Deciders:** Backend lead, Security lead
- **Related:** ADR-0002 (local DB), ADR-0003 (role claim refresh)

---

## Context

FieldProof holds several long-lived secrets:

- `JWT_SECRET` — signs access tokens
- Postgres password — authenticates the app to the database
- SQLCipher DB key (mobile) — encrypts the local attendance queue

A secret that never rotates is a secret that grows more valuable the
longer it stays in use. If any one of them leaks, the window of
exposure is the time between leak and detection, and detection is not
guaranteed.

Rotation shrinks the window. It is a control against silent compromise
as much as against active attack.

---

## Decision

**JWT_SECRET rotates every 90 days.**

- The new secret is written to Secrets Manager.
- Running processes continue using the old secret until restart.
- After restart, all previously issued tokens fail signature
  verification. Users re-authenticate.
- No downtime. The cost is one forced re-login per active session.

**Database password rotates every 90 days using a two-phase swap.**

1. Generate a new password.
2. Update the Postgres role to accept it *in addition to* the old
   one — this is not natively supported by Postgres, so we use a
   different shape: update Secrets Manager with the new password
   while the DB still has the old one, roll the app, then flip the DB.
   See the procedure below.
3. After every app instance is running with the new password, rotate
   the DB role itself.

The window where old and new passwords both work is as short as the
slowest rolling restart.

**SQLCipher key rotates on device revocation or wipe.** Rotating on a
schedule is not useful here — the key is device-bound and never leaves
the device. The threat is device loss, and the response is revocation.

---

## Two-phase DB password rotation (the actual procedure)

Phase 1 — prepare:

1. Generate a new password.
2. Write it to Secrets Manager under a new field `database_password_next`.
3. Do not change the DB role yet.

Phase 2 — cut over:

4. Update the DB role to the new password:
   `ALTER ROLE postgres WITH PASSWORD '<new>';`
5. Rolling restart of app instances. Existing connections use the old
   password until they close. New connections fail until the restart
   completes.
6. Once every instance is running the new password, delete the
   `database_password_next` field from Secrets Manager.

The order matters: Secrets Manager must know the new password before
the DB accepts it, otherwise the restart cannot authenticate.

---

## Alternatives considered

- **Never rotate.** Rejected. The cost of a leak grows linearly with
  time. For a system that holds attendance and location data for
  field workers, that is not acceptable.

- **Rotate on every restart.** Rejected. There is no benefit to a
  shorter interval than the rate at which a leak could be exploited.
  90 days is the industry norm and matches AWS defaults.

- **Rotate on demand, no schedule.** Rejected. Without a schedule,
  rotation never happens. The schedule is what makes it a control.

- **Dual JWT secrets with overlap.** Sign with the new secret, verify
  with either old or new for a window. Rejected: complicates the auth
  path, and a forced re-login every 90 days is cheap.

- **Hot reload of secrets without restart.** Rejected for S5. The
  loader is `lru_cache`d per process. Hot reload requires a file
  watcher or an SNS subscription; that is S14 work.

---

## Consequences

- A `JWT_SECRET` rotation forces every active session to re-authenticate.
  Users see the login screen once every 90 days. Acceptable.
- A DB password rotation requires a rolling restart. In a single-instance
  deployment there is a short window of connection failure. That is
  documented and accepted for MVP.
- Both rotation scripts are runnable manually. A scheduler (S14) drives
  them on the interval.
- The mobile SQLCipher key rotation is a separate mobile operation
  (S5 Day 6).

---

## Verification

- `scripts/rotate_jwt_secret.py` — rotates the JWT secret in Secrets Manager
- `scripts/rotate_db_password.py` — two-phase DB password rotation
- `tests/test_rotation.py` — proves both scripts produce the expected
  state changes and refuse to run when preconditions are not met

---

## Not covered

- **Automatic scheduling.** S14.
- **Rotation audit log.** Secrets Manager records API calls. The
  authorization_events table is not used for this.
- **Client revocation on rotation.** If the mobile app cached a JWT,
  it will fail after the JWT secret rotates. The 401 handler already
  forces re-login. No change needed.
