"""Audit chain integrity tests.

Proves the chain:
  - is intact after normal writes
  - detects a modification to a row's content
  - verify endpoint requires sys_admin
  - verify endpoint returns ok for sys_admin
"""

import os
import sys
import time
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AuthorizationEvent, Tenant, User  # noqa: E402
from app.services.audit import verify_chain  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_user(role: str) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"chain-{stamp}@example.com"
    db = SessionLocal()
    t = Tenant(name=f"Chain {stamp}")
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    db.add(u)
    db.commit()
    out = {"email": email, "id": u.id}
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_chain_intact_after_writes():
    httpx.get(f"{BASE}/attendance/admin/summary")  # 401
    user = _make_user("employee")
    token = _login(user["email"])
    httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))  # 403

    result = verify_chain()
    assert result["breaks"] == [], f"chain broken: {result['breaks']}"


def test_modification_detected():
    httpx.get(f"{BASE}/attendance/admin/summary")
    db = SessionLocal()
    row = (
        db.query(AuthorizationEvent)
        .order_by(AuthorizationEvent.id.desc())
        .first()
    )
    original_reason = row.reason
    row.reason = "tampered"
    db.commit()
    row_id = row.id
    db.close()

    try:
        result = verify_chain()
        assert any(b["id"] == row_id for b in result["breaks"]), result
    finally:
        db = SessionLocal()
        row = db.get(AuthorizationEvent, row_id)
        row.reason = original_reason
        db.commit()
        db.close()

    # Restore the chain to a valid state for subsequent tests.
    import subprocess
    subprocess.run(
        [sys.executable, "scripts/backfill_audit_chain.py"],
        check=True,
    )


def test_verify_endpoint_requires_sys_admin():
    user = _make_user("employee")
    token = _login(user["email"])
    r = httpx.get(f"{BASE}/audit/verify", headers=_auth(token))
    assert r.status_code == 403


def test_verify_endpoint_returns_ok_for_sys_admin():
    admin = _make_user("sys_admin")
    token = _login(admin["email"])
    r = httpx.get(f"{BASE}/audit/verify", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["breaks"] == []
