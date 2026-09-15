# FieldProof — Threat Register

- **Version:** 1.0
- **Date:** 2026-09-09
- **Sprint:** S0
- **Method:** STRIDE applied per element against the S0 DFD
- **Risk score:** Likelihood × Impact (1–5 each). Score ≥ 10 = high priority.

Every story must reference at least one threat ID below. If a story
introduces a new attack surface, add a row here before the story is Ready.

---

## Register

| ID | Element | STRIDE | Threat | Mitigation | Test | Risk | Status |
|----|---------|--------|--------|------------|------|------|--------|
| T-001 | POST /auth/login | S | Credential stuffing / brute force | Rate limit 10/min + account lockout after 5 fails | `hydra -l admin -P rockyou.txt` → expect 429 | 4×4=16 | Open |
| T-002 | POST /auth/login | I | Error message reveals whether email exists | Generic "invalid credentials" for both cases | Send valid + invalid email, compare responses | 3×2=6 | Open |
| T-003 | POST /attendance/events | T | Latitude/longitude modified in transit | Ed25519 signature over canonical payload | Tamper payload, keep signature → expect 400 | 4×4=16 | Open |
| T-004 | POST /attendance/events | T | Replay of old check-in event | Unique `idempotency_key` + `previous_event_hash` chain | Replay same event → expect `duplicate` | 4×3=12 | Open |
| T-005 | POST /attendance/events | S | Forged event from a device that is not registered | Verify signature against `devices.public_key`; reject if revoked | POST with unknown signature → expect 401 | 3×5=15 | Open |
| T-006 | GET /attendance/events/{id} | I | BOLA — read another user's event | Server-side check: event.user_id == principal.id or role allows | Cross-user GET → expect 403 | 4×5=20 | Open |
| T-007 | GET /reports/* | I | Cross-tenant read | `tenant_id` derived from principal, never from request | Tenant A token, tenant B data → expect 403 | 3×5=15 | Open |
| T-008 | POST /admin/* | E | BFLA — employee calls supervisor endpoint | `require_role()` dependency on every privileged route | Employee token → expect 403 | 3×5=15 | Open |
| T-009 | POST /attendance/events | R | Employee denies check-in; no evidence | `previous_event_hash` chain + audit log | Inspect audit trail after event | 2×3=6 | Open |
| T-010 | Sync endpoint | D | Flood sync endpoint | Rate limit per device + queue drain cap | 200 rapid POSTs → expect 429 | 3×3=9 | Open |
| T-011 | Local SQLCipher DB | T | Attendance row edited on rooted device | SQLCipher + per-event signature verified server-side | Modify row, trigger sync → expect 400 | 3×4=12 | Open |
| T-012 | Device registration | S | Fake device registered via replayed attestation | Verify Play Integrity / App Attest server-side; bind to user_id | Replay old attestation token → expect 401 | 3×4=12 | Open |
| T-013 | AI prompt | I | PII or biometric data enters LLM context | Allowlist fields, minimize, never send Restricted | Inspect prompt payload in test | 3×5=15 | Open |
| T-014 | AI endpoint | D | Cost abuse — expensive requests | Auth + per-tenant quota + token cap | 100 rapid AI calls → expect 429 | 3×3=9 | Open |
| T-015 | JWT | S | Stolen token used after logout | Short TTL (1h) + refresh rotation + server-side revoke list | Reuse token after logout → expect 401 | 3×4=12 | Open |

---

## Threat × Sprint mapping

| Threat | Sprint that closes it |
|--------|----------------------|
| T-001, T-002 | S3 (auth) + S6 (rate limit) |
| T-003, T-004 | S2 (signed events + idempotency) |
| T-005, T-012 | S3 (device binding) + S11 (attestation) |
| T-006, T-007, T-008 | S3 (RBAC + tenant isolation) |
| T-009 | S2 (hash chain) + S7 (audit) |
| T-010 | S6 (rate limit) |
| T-011 | S1 (SQLCipher) + S2 (signature) |
| T-013, T-014 | S20–S23 (AI security) |
| T-015 | S3 (JWT) + S6 (revocation) |

---

## How to use this register

1. Before marking a story Ready, add a line: `Threats: T-00X, T-00Y`.
2. If none of the existing threats apply, write a new row **first**.
3. Every mitigation must name a **test** — not "review the code".
4. Re-review the register at the start of each sprint. Threats drift.
