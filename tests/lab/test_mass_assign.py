"""Lab test: Mass Assignment on PATCH /lab/profile/update.

After the fix: only allowlisted fields (email, team_id) are writable.
A request containing `role`, `tenant_id`, or `is_active` returns 400 or
422, and the user row is unchanged.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
"""

import os
import sys
import time
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LAB_TESTS") != "1",
    reason="lab tests run only with RUN_LAB_TESTS=1",
)


def _make_user() -> str:
    """Create a fresh employee in their own tenant. Return the email."""
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 1000
    email = f"massassign-{stamp}@example.com"
    db = SessionLocal()
    t = Tenant(name=f"MassAssign {stamp}")
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role="employee",
    )
    db.add(u)
    db.commit()
    db.close()
    return email


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login",
                   json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _me(token: str) -> dict:
    r = httpx.get(f"{BASE}/auth/me",
                  headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def test_role_escalation_is_blocked():
    email = _make_user()
    token = _login(email)

    before = _me(token)
    assert before["role"] == "employee"

    r = httpx.patch(
        f"{BASE}/lab/profile/update",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "sys_admin"},
    )

    after = _me(token)

    if r.status_code == 200:
        pytest.fail(f"escalation succeeded: role is now {after['role']!r}")

    assert r.status_code in (400, 422), r.text
    assert after["role"] == "employee", (
        f"role changed despite rejection: {after['role']!r}"
    )


def test_tenant_change_is_blocked():
    email = _make_user()
    token = _login(email)

    before = _me(token)
    original_tenant = before["tenant_id"]

    r = httpx.patch(
        f"{BASE}/lab/profile/update",
        headers={"Authorization": f"Bearer {token}"},
        json={"tenant_id": original_tenant + 1},
    )

    after = _me(token)

    if r.status_code == 200:
        pytest.fail(
            f"tenant change succeeded: tenant is now {after['tenant_id']}"
        )

    assert r.status_code in (400, 422), r.text
    assert after["tenant_id"] == original_tenant, (
        f"tenant changed despite rejection: "
        f"{original_tenant} -> {after['tenant_id']}"
    )


def test_is_active_change_is_blocked():
    email = _make_user()
    token = _login(email)

    r = httpx.patch(
        f"{BASE}/lab/profile/update",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )

    if r.status_code == 200:
        # If accepted, the user should be deactivated and /auth/me
        # should fail with 401.
        r2 = httpx.get(f"{BASE}/auth/me",
                       headers={"Authorization": f"Bearer {token}"})
        if r2.status_code != 200:
            pytest.fail("is_active change succeeded")
        return

    assert r.status_code in (400, 422), r.text
