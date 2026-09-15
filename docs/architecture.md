# FieldProof — Architecture (S0 Baseline)

- **Version:** 1.0
- **Date:** 2026-09-09
- **Sprint:** S0
- **Status:** Approved baseline

---
## 1. System context (C4 Level 1)

```mermaid
graph TD
    Employee[Employee<br/>mobile app]
    Supervisor[Supervisor<br/>mobile app]
    HR[HR / Ops<br/>web dashboard]
    SecAdmin[Security Admin<br/>web dashboard]

    FP[FieldProof Platform]

    LLM[LLM Provider<br/>external]
    Attest[Play Integrity /<br/>App Attest]
    SMS[SMS Provider]

    Employee --> FP
    Supervisor --> FP
    HR --> FP
    SecAdmin --> FP

    FP --> LLM
    FP --> Attest
    FP --> SMS

    classDef ext fill:#f9f,stroke:#333,stroke-dasharray: 5 5
    class LLM,Attest,SMS ext
```

**Trust note:** every external boundary (LLM, Attest, SMS) is untrusted.
Data leaving FieldProof must be minimized and authorized.

---
## 2. Container diagram (C4 Level 2)

```mermaid
graph TD
    subgraph Mobile["Flutter Mobile (untrusted device)"]
        UI[UI<br/>Widgets only]
        BLoC[BLoC<br/>event → state]
        Repo[Repository]
        Dio[Dio Client<br/>auth + req ID]
        Queue[(SQLCipher<br/>attendance queue)]
        KeyStore[(KeyStore<br/>HW-backed)]
    end

    subgraph Backend["FastAPI Backend (trusted)"]
        API[API Gateway<br/>JWT + RBAC]
        Svc[Service Layer<br/>authorization]
        RepoDB[Repository<br/>tenant-scoped]
        LLMProxy[LLM Proxy<br/>allowlist + quota]
    end

    DB[(PostgreSQL)]
    Redis[(Redis)]
    LLM[LLM Provider]

    UI --> BLoC --> Repo
    Repo --> Dio
    Repo --> Queue
    Queue -. key .-> KeyStore

    Dio -->|signed HTTPS| API
    API --> Svc --> RepoDB --> DB
    API --> Redis
    Svc --> LLMProxy --> LLM

    classDef untrusted fill:#ffe6e6,stroke:#c00
    classDef trusted fill:#e6ffe6,stroke:#060
    class Mobile untrusted
    class Backend trusted
```

**Red = untrusted. Green = trusted.** The device is untrusted. The backend is trusted. Data crossing between them is validated server-side.

---
## 3. Attendance check-in flow (data flow, trust boundaries)

```mermaid
sequenceDiagram
    participant U as User
    participant App as Flutter App
    participant DB as SQLCipher
    participant API as FastAPI
    participant PG as PostgreSQL

    U->>App: tap Check In
    App->>App: build canonical payload
    App->>App: sign with device private key
    App->>DB: INSERT attendance_queue<br/>(signature, prev_hash, idempotency_key)

    Note over App,DB: Offline — queue holds until network

    App->>API: POST /attendance/events<br/>Authorization + Idempotency-Key
    API->>API: verify JWT (principal)
    API->>API: verify signature vs devices.public_key
    API->>API: verify previous_event_hash chain
    API->>PG: INSERT attendance_events
    API-->>App: 201 accepted
    App->>DB: UPDATE sync_status='synced'
```

**Trust boundaries crossed:**
1. User → App (device untrusted)
2. App → API (network untrusted)
3. API → DB (trusted, parameterized)

**Rule:** every event is signed on-device and verified server-side. The local DB is a queue; the server is truth.

---
## 4. Trust boundary rules

| Boundary | Rule |
|----------|------|
| Device → API | Every request carries JWT. Server verifies principal. Never trust `user_id`/`tenant_id` from body. |
| App → Local DB | SQLCipher with HW-backed key. Every event signed. |
| API → LLM | Allowlist fields. No Restricted class. Backend proxy only. |
| API → DB | Parameterized queries. `tenant_id` from principal, never request. |

---

## 5. Data classification summary

See `docs/DATA_CLASSIFICATION.md`.

| Class | Where it lives | Crosses boundary? |
|-------|---------------|-------------------|
| P0 Public | Anywhere | Yes |
| P1 Internal | Backend, logs (P1-only) | Yes |
| P2 Confidential | Backend, encrypted at rest | Minimized |
| P3 Restricted | Backend proxy only, HW key | No client read path |
| Secret | Secure storage / secrets manager | Never |

---

## 6. Deployment topology (S0 local)

```mermaid
graph LR
    Dev[Dev laptop] -->|docker compose| DB[(Postgres 16)]
    Dev --> Redis[(Redis 7)]
    Dev -->|flutter run| Emu[Android emulator]
    Emu -->|10.0.2.2:8000| Dev
```

Production topology (AWS) defined in S15 (Terraform).

---

## 7. References

- ADR-0001 — state management
- ADR-0002 — local database
- `docs/security/threat_register.md`
- `docs/DATA_CLASSIFICATION.md`