"""Deliberately vulnerable code for S4 AppSec lab.

DO NOT import anything from this package in production code.
DO NOT mount the lab router unless ENVIRONMENT=lab.

Every vulnerability in this module is:
  1. Documented in docs/security/s4-appsec-lab.md
  2. Covered by a test in tests/lab/ that triggers it
  3. Fixed in the same sprint

See ADR-0001 (BLoC) and the S4 sprint plan for context.
"""
