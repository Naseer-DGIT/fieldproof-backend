# S6 — ZAP Authenticated API Scan

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 4)
- **Target:** `http://localhost:8000` (lab mode)
- **Tool:** OWASP ZAP `zap-api-scan.py`
- **Auth:** Bearer token injected via a replacer rule
- **Spec:** `/openapi.json`
- **Token:** seed user (`test@example.com`), role `employee`

---

## Method

The API scan reads the OpenAPI spec and issues requests against every
documented route. A ZAP replacer rule adds
`Authorization: Bearer <token>` to every request.

Because the token is an `employee`, the scan reaches employee-level
routes:

- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/devices/register`
- `GET /api/v1/devices/me`
- `POST /api/v1/attendance/events`
- `GET /api/v1/attendance/events`
- `GET /api/v1/attendance/events/{event_id}`

Routes requiring `supervisor`, `hr_ops`, or `sys_admin` return 403. The
Day 3 manual pentest covered those.

---

## Command
