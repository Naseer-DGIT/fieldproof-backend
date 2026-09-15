# ADR-0002: Local Database — Single Encrypted SQLCipher DB

- **Status:** Accepted
- **Date:** 2026-09-09
- **Sprint:** S0 → S1
- **Deciders:** Mobile lead, Security lead
- **Related:** ADR-0001

## Context

FieldProof is offline-first. Attendance events must be queued locally with no
network, survive process death and reboot, and sync later without loss,
duplication, or reordering. The local store is on the critical path for every
core feature — not a cache.

A stolen device or extracted backup must not expose attendance history,
device keys, or payloads. The device is untrusted by design. The local DB is
a **queue and evidence cache**, not the source of truth.

## Decision

Use **one** encrypted database, opened with **SQLCipher**, for all local
persistent state: offline attendance queue, app state, cached read models.

**No second local database. No unencrypted key-value store. No second
persistence path.**

The DB key is a **randomly generated 256-bit key**, stored in hardware-backed
secure storage (Keychain / Keystore). It is **not derived from a user
password, PIN, or device identifier**.

## Alternatives considered

- **Dual local databases** (e.g., SQLCipher + `hydrated_bloc`/Hive) —
  rejected. ADR-0001 deferred `hydrated_bloc`. ADR-0002 finalizes it:
  `hydrated_bloc` is not used. Its default Hive storage is unencrypted. A
  second store would fragment the queue into an unauditable side channel.
- **Password-derived key** — rejected. The app must open cold, offline,
  before user input. There is no password at open time. Derivation would
  force an unlock gesture before background sync and would tempt us into
  storing a salt/verifier locally.
- **Plain SQLite** — rejected. A stolen device exposes attendance + PII.

## Key generation

Random 32-byte key via `Random.secure()`, base64url-encoded, written to
`flutter_secure_storage` with `first_unlock_this_device`. On Android uses
`EncryptedSharedPreferences`.

**Why random:** decouples the DB from any user secret. App opens at boot,
syncs in background, runs in CI.

**Costs:**
1. **No recovery if secure storage is wiped.** Accepted — the queue is a
   synced cache; the server holds the authoritative record.
2. **Device-bound, not portable.** Restoring to a new device requires
   re-registration. Accepted — portability would require exporting the key.
3. **No password change to rotate.** Rotation is an explicit `PRAGMA rekey`
   operation, scheduled later.

## Package choice (checked 2026-09-09)

**Chosen:** `sqflite_sqlcipher` — latest version **3.4.1**, published
**2026-08-04** on pub.dev. Bundles SQLCipher 4.10.0 on Android/iOS/macOS,
actively maintained, exposes `sqflite`-compatible API.

**Rejected:** `sqlcipher_flutter_libs` — `0.7.0+eol`, published
**2026-02-15**. Deprecated and non-functional per package README.

**Noted for later:** `package:sqlite3` v3.x can enable SQLCipher via build
hooks (`user_defines: sqlite3: source: sqlcipher`). Relevant if we adopt
`drift` for typed queries.

Re-verify package version and pub.dev status at each sprint review.

## Security implications

1. **Encryption protects data at rest.** A stolen device, extracted backup,
   or filesystem dump yields ciphertext only. It does not protect data while
   the app runs.
2. **Encryption does not protect against a compromised app process.** If an
   attacker injects code (Frida, repackaged APK, root), they run inside the
   process that holds the key. The key is in memory. This is a limit of any
   client-side encryption.
3. **That limit is why the local DB is not truth.** The server must not
   trust a synced event just because it came from an encrypted store.
   Therefore:
   - Every attendance event is **signed on-device** with a private key in
     hardware-backed storage, never exported.
   - Events carry `previous_event_hash`, forming a tamper-evident chain.
   - The server verifies signature, chain, idempotency, monotonic time.
   - The client DB is a **queue**; the server is the **authoritative record**.

## Consequences

- All local persistence goes through `AppDatabase`. No other storage plugin
  may persist application state.
- `hydrated_bloc` removed from S2 consideration.
- Key loss = re-registration, not support escalation.
- DB key rotation tracked as security debt with a target sprint.
- Package version + pub.dev check date recorded; re-check each sprint.

## References

- ADR-0001 — state management
- `docs/security/threat_register.md` — T-004, T-011
- pub.dev check 2026-09-09: `sqflite_sqlcipher` 3.4.1 (2026-08-04);
  `sqlcipher_flutter_libs` 0.7.0+eol (2026-02-15, deprecated)
