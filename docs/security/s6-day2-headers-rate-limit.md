# S6 Day 2 — Security Headers and Rate Limiting

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 2)
- **Related:** s6-zap-baseline.md

## What changed

### Security headers

`app/core/security_headers.py::SecurityHeadersMiddleware` adds four
headers to every response:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` |

The CSP is a JSON API default. It is safe because the API does not
serve HTML. If a future endpoint serves HTML, that endpoint sets its
own CSP.

The middleware is added first so it applies to error responses too.

### Rate limiting

`slowapi` with an in-memory store, keyed on the client IP.

| Endpoint | Limit |
|----------|-------|
| `POST /auth/login` | 10/minute |
| `POST /attendance/events` | 60/minute |

A 429 response is returned when the limit is exceeded.

## ZAP after the fix

<PASTE THE UPDATED ALERT LIST OR A SUMMARY>

## Tests

- `tests/test_security_headers_baseline.py` — 5 tests
- `tests/test_rate_limit.py` — 1 test

## Not covered

- **Rate limit persistence.** The limiter uses an in-process store.
  A rolling restart resets the count. Redis-backed storage is S14.
- **IP spoofing behind a proxy.** `get_remote_address` reads
  `request.client.host`. Behind a proxy it returns the proxy address.
  X-Forwarded-For handling is S15.
