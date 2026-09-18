# ADR-0003: Role Claim Refresh — Versioned Role Check

- **Status:** Accepted
- **Date:** 2026-09-17
- **Sprint:** S3 (Day 5)
- **Deciders:** Backend lead, Security lead
- **Related:** ADR-0001 (state management), ADR-0002 (local DB)

---

## Context

FieldProof issues JWTs with a 1-hour TTL. The token carries `sub`,
`tenant`, and `role`. Authorization decisions (`require_role`,
`require_min_role`) read the role from the token.

If a user's role changes in the database — for example, a supervisor is
demoted to employee after an incident — the old token continues to
grant supervisor access until it expires. The window is up to 1 hour.

In a system that governs attendance and pay, a demoted supervisor
retaining team-wide read access for up to 60 minutes is not
acceptable. The window must be closed without introducing a database
read on every request that defeats the purpose of JWT.

---

## Decision

Add a `role_version` integer column to `users`. Increment it whenever
`role` (or `tenant_id`, or `is_active`) changes. Include the current
`role_version` in every JWT as a claim. On each authenticated request,
`get_current_user` compares the claim to the row and rejects with 401
if they differ.

The comparison is a single indexed column read, not a full row fetch.
It is acceptable to cache this value in Redis later (S14) if the read
becomes a bottleneck.

---

## Alternatives considered

- **Accept the window.** Documented and simple. Rejected: the cost of
  a demoted supervisor retaining access is higher than the cost of one
  indexed read.

- **Read the full row on every request.** Simple and correct, but
  duplicates work that JWT was designed to avoid. Rejected in favor of
  the narrower version check.

- **Maintain a revocation list.** Keep the tokens; publish a list of
  revoked `sub` values. Rejected: the list itself becomes a database,
  and revocation must be propagated to every server. The version check
  is a single integer.

- **Shorten JWT TTL to 5 minutes.** Reduces the window but does not
  close it, and forces a token refresh on every short network gap.
  Rejected.

---

## Consequences

- `users.role_version` column added (integer, NOT NULL, default 0)
- JWT gains a `rv` claim
- `get_current_user` performs one indexed read per authenticated request
- Any code path that changes `role`, `tenant_id`, or `is_active` must
  increment `role_version` in the same transaction
- A user can force a logout of all their sessions by incrementing the
  column (not exposed as an endpoint in S3)
- The old token scheme (no `rv` claim) is rejected with 401 rather than
  silently accepted, so a missing claim is not a bypass

## Follow-up

- S14: cache the `role_version` read in Redis if profiling shows it
  matters
- S14: add a "sign out all devices" endpoint that increments the column
- S15: include the version in audit logs when a role changes
