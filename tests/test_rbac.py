"""RBAC tests.

Uses a live test client against the real database. Creates a throwaway
tenant and two users, then exercises the new role-checked endpoint.
"""

import base64
import os
import sys
import time
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_user(role: str) -> tuple[str, str, int]:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 1000
    email = f"rbac-{stamp}@example.com"
    db = SessionLocal()
    tenant = Tenant(name=f"RBAC Tenant {stamp}")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    db.add(user)
    db.commit()
    tenant_id = tenant.id
    db.close()
    return email, PASSWORD, tenant_id


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_employee_cannot_read_admin_summary():
    email, pwd, _ = _make_user("employee")
    token = _login(email, pwd)
    r = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "Insufficient role"


def test_hr_ops_can_read_admin_summary():
    email, pwd, tenant_id = _make_user("hr_ops")
    token = _login(email, pwd)
    r = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == tenant_id
    assert body["event_count"] == 0
    assert body["generated_by"] == email


def test_sys_admin_can_read_admin_summary():
    email, pwd, _ = _make_user("sys_admin")
    token = _login(email, pwd)
    r = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))
    assert r.status_code == 200, r.text


def test_unauthenticated_gets_401():
    r = httpx.get(f"{BASE}/attendance/admin/summary")
    assert r.status_code == 401
