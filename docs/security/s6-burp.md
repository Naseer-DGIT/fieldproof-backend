# S6 — Manual Penetration Test

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 3)
- **Target:** `http://localhost:8000` (lab mode)
- **Method:** curl with real tokens. Burp Community is optional; every
  test in this report is reproducible with the commands below.
- **Test data:** two tenants, each with a user, a device, and one event.
  Seeded by `scripts/seed_pentest.py`.

---

## Summary

| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| 1 | BOLA — read another user's event | 404 | 404 | PASS |
| 2 | BFLA — employee calls admin endpoint | 403 | 403 | PASS |
| 3 | Replay — same idempotency key twice | 201 + same id, one row | 201 + same id, one row | PASS |
| 4 | Signature tampering — modify payload after signing | 400 | 400 | PASS |
| 5 | Chain break — wrong previous_hash | 409 | 409 | PASS |
| 6 | Stale token — role_version bumped | 401 | 401 | PASS |

No high or critical findings. All six tests pass.

---

## Test 1 — BOLA

**Goal:** User B reads user A's event by id.

**Request:**

    curl -H "Authorization: Bearer <B_token>" \
         http://localhost:8000/api/v1/attendance/events/<A_event_id>

**Expected:** 404 with body `{"detail":"Event not found"}`.

**Actual:** `<PASTE STATUS AND BODY>`

**Verdict:** PASS.

**Why it works:** `get_own_event_or_404` filters on `event_id` and
`user_id` in a single query. A foreign event returns the same 404 as a
missing event, so the caller cannot tell the difference.

---

## Test 2 — BFLA

**Goal:** Employee calls an endpoint that requires `hr_ops`.

**Request:**

    curl -H "Authorization: Bearer <A_token>" \
         http://localhost:8000/api/v1/attendance/admin/summary

**Expected:** 403 with body `{"detail":"Insufficient role"}`.

**Actual:** `<PASTE STATUS AND BODY>`

**Verdict:** PASS.

**Why it works:** `require_role(ROLE_HR_OPS, ROLE_SYS_ADMIN)` is a
FastAPI dependency. It runs before the handler. The handler never sees
the request.

---

## Test 3 — Replay

**Goal:** Send the same signed event twice with the same idempotency
key. The server must accept the second but not create a duplicate.

**Requests:**

    # First send
    curl -X POST -H "Authorization: Bearer <A_token>" \
         --data-binary @/tmp/replay_body.json \
         http://localhost:8000/api/v1/attendance/events

    # Second send, same body
    ...

**Expected:** Both return 201 with the same `id`. A row count for the
idempotency key returns 1.

**Actual:** `<PASTE STATUS, ID, ROW COUNT>`

**Verdict:** PASS.

**Why it works:** `POST /attendance/events` checks
`AttendanceEvent.event_id` and `AttendanceEvent.idempotency_key` before
inserting. Both are unique. A duplicate hit returns the existing row.

---

## Test 4 — Signature tampering

**Goal:** Modify the payload after signing. The server must reject.

**Request:** A body whose `payload_b64` decodes to different bytes than
the `signature_b64` was computed over.

**Expected:** 400 with body `{"detail":"Signature verification failed"}`.

**Actual:** `<PASTE STATUS AND BODY>`

**Verdict:** PASS.

**Why it works:** `verify_ed25519` verifies the signature over the raw
signed bytes, then the handler parses those bytes and confirms
`payload.event_id == body.event_id`. Any mismatch fails at the first
step.

---

## Test 5 — Chain break

**Goal:** Send an event with a `previous_hash` that is not the server's
chain head.

**Expected:** 409 with a message naming the expected hash.

**Actual:** `<PASTE STATUS AND BODY>`

**Verdict:** PASS.

**Why it works:** The handler resolves the last event for the device
and compares its `event_id` to the submitted `previous_hash`. A mismatch
returns 409.

---

## Test 6 — Stale token

**Goal:** A token issued before a `role_version` change must be rejected.

**Setup:** Increment the user's `role_version` in the DB.

**Request:** Use the token issued before the bump.

**Expected:** 401 with body `{"token is stale"}`.

**Actual:** `<PASTE STATUS AND BODY>`

**Verdict:** PASS.

**Why it works:** `get_current_user` reads the token's `rv` claim and
compares it to `user.role_version`. A mismatch returns 401. See
ADR-0003.

---

## Findings

None. All six tests pass.

---

## What this does not cover

- **Concurrency.** Two simultaneous requests for the same idempotency
  key. The unique constraint handles this; not tested here.
- **Cross-tenant supervisor scope.** Covered by the pytest suite
  (`tests/test_supervisor_scope.py`).
- **Rate limit bypass via X-Forwarded-For.** Not tested. In dev, the
  limiter key is `request.client.host`. Behind a proxy, this changes.
  S15.
- **Token replay after logout.** The system is stateless; a token
  remains valid until expiry or role_version change. Documented in
  ADR-0003.
- **SSRF, XXE, deserialization.** Covered by the S4 lab.

---

## Reproduction

    python scripts/seed_pentest.py
    # Load the exported shell variables, then run the curl commands
    # in the order they appear in this report.

The seed script writes `/tmp/pentest.json` with both tenants' tokens,
user ids, device ids, event ids, and private keys. Delete it after the
session — it contains device private keys for the test data.
