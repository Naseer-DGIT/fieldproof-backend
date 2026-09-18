"""Authorization audit log tests.

Proves that denied requests land in the authorization_events table
with the correct reason, and that successful requests do not.
"""

import base64
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AuthorizationEvent, Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_user(role: str = "employee") -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"audit-{stamp}@example.com"
    db = SessionLocal()
    t = Tenant(name=f"Audit {stamp}")
    db.add(t); db.flush()
    u = User(tenant_id=t.id, email=email,
             password_hash=hash_password(PASSWORD), role=role)
    db.add(u); db.commit()
    out = {"email": email, "id": u.id, "tenant_id": t.id}
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _count_audit_rows_since(marker_id: int) -> list[AuthorizationEvent]:
    db = SessionLocal()
    try:
        rows = (
            db.query(AuthorizationEvent)
            .filter(AuthorizationEvent.id > marker_id)
            .order_by(AuthorizationEvent.id.asc())
            .all()
        )
        return list(rows)
    finally:
        db.close()


def _max_audit_id() -> int:
    db = SessionLocal()
    try:
        row = db.query(AuthorizationEvent).order_by(AuthorizationEvent.id.desc()).first()
        return row.id if row else 0
    finally:
        db.close()


def test_401_is_audited():
    marker = _max_audit_id()
    r = httpx.get(f"{BASE}/attendance/admin/summary")
    assert r.status_code == 401

    rows = _count_audit_rows_since(marker)
    assert len(rows) == 1
    row = rows[0]
    assert row.status_code == 401
    assert row.user_id is None
    assert row.tenant_id is None
    assert "Authorization" in row.reason or "credentials" in row.reason.lower()
    assert row.endpoint == "/api/v1/attendance/admin/summary"


def test_403_is_audited_with_user():
    user = _make_user(role="employee")
    token = _login(user["email"])
    marker = _max_audit_id()

    r = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))
    assert r.status_code == 403

    rows = _count_audit_rows_since(marker)
    assert len(rows) == 1
    row = rows[0]
    assert row.status_code == 403
    assert row.user_id == user["id"]
    assert row.tenant_id == user["tenant_id"]
    assert row.reason == "Insufficient role"


def test_404_is_audited():
    user = _make_user(role="employee")
    token = _login(user["email"])
    marker = _max_audit_id()

    r = httpx.get(
        f"{BASE}/attendance/events/{uuid.uuid4()}",
        headers=_auth(token),
    )
    assert r.status_code == 404

    rows = _count_audit_rows_since(marker)
    assert len(rows) == 1
    row = rows[0]
    assert row.status_code == 404
    assert row.reason == "Event not found"


def test_success_is_not_audited():
    user = _make_user(role="employee")
    token = _login(user["email"])
    marker = _max_audit_id()

    r = httpx.get(f"{BASE}/auth/me", headers=_auth(token))
    assert r.status_code == 200

    rows = _count_audit_rows_since(marker)
    assert rows == []


def test_stale_token_is_audited():
    """The role-version change path from Day 5 also gets audited."""
    user = _make_user(role="employee")
    token = _login(user["email"])

    # Bump role_version
    db = SessionLocal()
    u = db.get(User, user["id"])
    u.role_version = u.role_version + 1
    db.commit()
    db.close()

    marker = _max_audit_id()
    r = httpx.get(f"{BASE}/auth/me", headers=_auth(token))
    assert r.status_code == 401

    rows = _count_audit_rows_since(marker)
    assert len(rows) == 1
    assert rows[0].status_code == 401
    assert "stale" in rows[0].reason.lower()
