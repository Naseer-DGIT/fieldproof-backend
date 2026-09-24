# S5 — Secrets Management

- **Date:** 2026-09-24
- **Sprint:** S5 (Day 2)
- **Author:** Naseer
- **Related:** ADR-0003, threat_register.md

---

## What changed

`JWT_SECRET` and the database password no longer come from plain
environment variables in staging and prod. They come from AWS Secrets
Manager. Dev and lab read from environment variables with safe
defaults so a fresh clone runs `pytest` with no setup.

One JSON secret per environment:
