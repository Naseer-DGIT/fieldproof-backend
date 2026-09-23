# S4 — AppSec Lab Report

- **Sprint:** S4
- **Author:** Naseer
- **Related:** threat_register.md, DATA_CLASSIFICATION.md
- **Purpose:** Deliberate vulnerabilities in `app/lab/`, each with a
  proof-of-concept test, a fix, and a verification. The final state of
  every lab module is fixed.

The lab modules are mounted only when `ENVIRONMENT=lab`. They are never
part of the production app.

---

# Lab 1 — SQL Injection

- **Class:** CWE-89
- **OWASP Top 10:2021:** A03 Injection
- **Location:** `app/lab/sqli.py`, `search_users`
- **Endpoint:** `GET /api/v1/lab/sqli/search?q=...`
- **Status:** Fixed

## Root cause

The `q` parameter was interpolated into a raw SQL string:

```python
sql = f"SELECT id, email, role FROM users WHERE email LIKE '%{q}%' LIMIT 500"
rows = db.execute(text(sql)).fetchall()

---

# Lab 4 — Insecure Deserialization (pickle)

- **Class:** CWE-502
- **OWASP Top 10:2021:** A08 Software and Data Integrity Failures
- **Location:** `app/lab/pickle_load.py`, `load_pickle`
- **Endpoint:** `POST /api/v1/lab/pickle/load`
- **Status:** Fixed

## Root cause

The endpoint accepted base64-encoded bytes and called `pickle.loads`:

```python
obj = pickle.loads(raw)

---

# Lab 5 — Server-Side Request Forgery (SSRF)

- **Class:** CWE-918
- **OWASP API Top 10:2023:** API7 SSRF
- **Location:** `app/lab/ssrf.py`, `fetch_url`
- **Endpoint:** `GET /api/v1/lab/ssrf/fetch?url=...`
- **Status:** Fixed

## Root cause

The endpoint passed the caller's `url` directly to an HTTP client:

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url)

---

# Lab 6 — Mass Assignment / Property Authorization

- **Class:** CWE-915
- **OWASP API Top 10:2023:** API3 Broken Object Property Level Authorization
- **Location:** `app/lab/mass_assign.py`, `update_profile`
- **Endpoint:** `PATCH /api/v1/lab/profile/update`
- **Status:** Fixed

## Root cause

The endpoint accepted a full `User` shape from the client and copied
every supplied field onto the model:

```python
updates = body.model_dump(exclude_unset=True)
for field, value in updates.items():
    setattr(user, field, value)
