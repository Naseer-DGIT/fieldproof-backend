# S6 — Attack Tree: POST /api/v1/attendance/events

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 6)
- **Related:** ADR-0002, ADR-0003, `threat_register.md`

The attack tree starts from the attacker's goal and branches into every
way to reach it. Each leaf is either:

- **Blocked** by an existing control (with the control named)
- **Detected** by an existing signal (with the signal named)
- **Open** and tracked as a finding or accepted limitation

---

## Goal

**G1: Insert an attendance event that the server accepts but the employee did not perform.**

This is the highest-value goal: a forged event becomes a payroll record.
The attacker can be the employee (self-service fraud), an external
attacker with a stolen token, or an insider with database access.

---

## Tree
