"""Role-version refresh tests (ADR-0003).

A JWT issued before a role change must be rejected with 401 after the
change, even though the token's own expiry has not passed.
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


def _make_user(role: str = "employee", team_id: int | None = None) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"rv-{stamp}@example.com"
    db = SessionLocal()
    t = Tenant(name=f"RV Tenant {stamp}")
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        team_id=team_id,
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


def _bump_role_version(user_id: int, new_role: str) -> None:
    db = SessionLocal()
    u = db.get(User, user_id)
    u.role = new_role
    u.role_version = u.role_version + 1
    db.commit()
    db.close()


def _me(token: str) -> httpx.Response:
    return httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_token_valid_before_change():
    user = _make_user("employee")
    token = _login(user["email"])
    r = _me(token)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "employee"


def test_token_rejected_after_role_change():
    user = _make_user("employee")
    token = _login(user["email"])

    # Token works
    assert _me(token).status_code == 200

    # Role changes in the DB
    _bump_role_version(user["id"], "supervisor")

    # Old token is now stale
    r = _me(token)
    assert r.status_code == 401, r.text
    assert "stale" in r.json()["detail"].lower()


def test_new_login_after_change_works():
    user = _make_user("employee")
    token = _login(user["email"])

    _bump_role_version(user["id"], "supervisor")

    # Old token rejected
    assert _me(token).status_code == 401

    # New login issues a token with the new rv
    fresh = _login(user["email"])
    r = _me(fresh)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "supervisor"


def test_token_without_rv_claim_is_rejected():
    """A token that was issued before ADR-0003 must not be silently
    accepted. It has no rv claim and must fail."""
    user = _make_user("employee")
    token = _login(user["email"])

    # Hand-craft a token with no rv to simulate a pre-ADR token
    import jwt as pyjwt
    from app.core.config import settings

    forged = pyjwt.encode(
        {
            "sub": str(user["id"]),
            "tenant": 1,
            "role": "employee",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            # no rv
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    r = _me(forged)
    assert r.status_code == 401
