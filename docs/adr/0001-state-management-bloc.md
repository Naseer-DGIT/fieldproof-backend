# ADR-0001: State Management — BLoC (flutter_bloc)

- **Status:** Accepted
- **Date:** 2026-09-09
- **Sprint:** S0 → S1
- **Deciders:** Mobile lead, Security lead
- **Related:** ADR-0002

## Context

FieldProof is offline-first. Every attendance action (check-in, check-out,
break start/stop, correction) must work with no network, produce a signed
event queued in SQLCipher, and be auditable. An attacker must not be able to
skip a state transition (check-out before check-in), and a reviewer must be
able to reconstruct exactly what happened.

This is an event-driven problem. The state layer must make every
security-relevant transition explicit, named, and testable without a device.

## Decision

Use **BLoC (`flutter_bloc`)** with three layers:

1. **Presentation** — Flutter widgets only. Dispatch events, render states.
   No Dio, no repository access, no business rules.
2. **Domain / Logic** — BLoC (event → state), use cases. Pure Dart. Owns
   authorization-before-action and offline queue policy (retry, ordering,
   idempotency).
3. **Data** — Repositories and data sources: Dio for network, SQLCipher for
   local queue, KeyStore for secrets. Only layer allowed to touch persistence.

## Alternatives considered

- **Riverpod** — read-heavy DI is excellent, but the `ref.watch` graph hides
  the full set of transitions. Cannot hand a reviewer an enumerable list of
  every attendance state change. Rejected.
- **Provider** — same problem with fewer guarantees. No event contract.
- **setState / ValueNotifier** — no separation of concerns. Widget code
  would call Dio directly, breaking the rule that authorization and offline
  policy live below the UI. Rejected on security grounds.
- **Redux** — single global store. Tenant isolation becomes convention, and
  devtools can capture sensitive state (tokens, payloads). Rejected.
- **MobX** — observable mutations are implicit; no named transition to test.
  Conflicts with offline tamper-evidence. Rejected.
- **GetX** — conflates routing, DI, state. No explicit event contract.

## Security implications

1. **Explicit event classes give an auditable, testable record of every
   security-state transition.** Each action is a named event
   (`CheckInRequested`, `EventSynced`). The event→state table is a
   replayable specification, testable without a device.
2. **Unidirectional flow prevents the UI from bypassing authorization.** A
   widget cannot call Dio; it can only dispatch an event. The BLoC decides
   whether the call is allowed, using the authenticated principal — never a
   client-supplied role or tenant_id.
3. **Deterministic transitions make offline replay defense provable.** A
   duplicate `CheckInRequested` with the same `previous_event_hash` must be
   dropped. This is provable in unit tests.

## Consequences

- Extra concept for developers coming from Riverpod/setState.
- More boilerplate (event + state classes). Accepted.
- Every story must declare events and states before implementation.
- `hydrated_bloc` deferred until offline persistence policy is finalized in
  ADR-0002 (now rejected — see ADR-0002).

## References

- `docs/security/threat_register.md` — T-004, T-011
- ADR-0002 — local database
