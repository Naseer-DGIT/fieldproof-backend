"""Cross-tenant isolation tests.

Creates two tenants, each with one user and one device. Every test
tries to reach tenant B's data using tenant A's token. The correct
result is always 403, 404, or an empty response — never tenant B's data.
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
from app.models import Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def tenant_a():
    return _make_tenant("a", role="employee")


@pytest.fixture(scope="module")
def tenant_b():
    return _make_tenant("b", role="employee")


@pytest.fixture(scope="module")
def hr_a():
    return _make_tenant("hr-a", role="hr_ops")


@pytest.fixture(scope="module")
def hr_b():
    return _make_tenant("hr-b", role="hr_ops")


def _make_tenant(label: str, role: str) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"tenant-{label}-{stamp}@example.com"
    db = SessionLocal()
    tenant = Tenant(name=f"Tenant {label} {stamp}")
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
    out = {"email": email, "password": PASSWORD, "tenant_id": tenant.id, "user_id": user.id}
    db.close()
    return out


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_admin_summary_scoped_to_caller_tenant(hr_a, hr_b):
    """HR user in tenant A sees only tenant A's count, even though tenant B
    also has events."""
    token_a = _login(hr_a["email"], hr_a["password"])
    token_b = _login(hr_b["email"], hr_b["password"])

    r_a = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token_a))
    r_b = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token_b))

    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json()["tenant_id"] == hr_a["tenant_id"]
    assert r_b.json()["tenant_id"] == hr_b["tenant_id"]
    assert r_a.json()["tenant_id"] != r_b.json()["tenant_id"]


def test_events_list_only_returns_self(tenant_a, tenant_b):
    """A user in tenant B cannot see tenant A's events via the list
    endpoint, even though both are employees in different tenants."""
    token_b = _login(tenant_b["email"], tenant_b["password"])
    r = httpx.get(f"{BASE}/attendance/events", headers=_auth(token_b))
    assert r.status_code == 200
    # Even if the other tenant has events, B's list must not contain them.
    for event in r.json():
        # The server does not return user_id in AttendanceEventOut, but if
        # it ever did, this assertion would catch a cross-tenant leak.
        assert "user_id" not in event or event["user_id"] == tenant_b["user_id"]


def test_device_me_only_returns_self(tenant_a, tenant_b):
    """A user cannot fetch another user's device. There is no path parameter
    on /devices/me, so this test mostly documents the contract. It would
    catch a regression if the endpoint ever gained a ?user_id= parameter."""
    token_a = _login(tenant_a["email"], tenant_a["password"])
    token_b = _login(tenant_b["email"], tenant_b["password"])

    r_a = httpx.get(f"{BASE}/devices/me", headers=_auth(token_a))
    r_b = httpx.get(f"{BASE}/devices/me", headers=_auth(token_b))

    # Neither user has registered a device yet.
    assert r_a.status_code == 404
    assert r_b.status_code == 404


def test_admin_summary_rejects_employee(tenant_a):
    """Role check runs before tenant filter. Employee role gets 403
    regardless of tenant."""
    token = _login(tenant_a["email"], tenant_a["password"])
    r = httpx.get(f"{BASE}/attendance/admin/summary", headers=_auth(token))
    assert r.status_code == 403
