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
