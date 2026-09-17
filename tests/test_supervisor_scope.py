"""Supervisor scope tests.

A supervisor sees events for their team only, inside their tenant.
Every boundary is tested: another team, another tenant, no team, wrong
role, no auth.
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
from app.models import Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"

TEAM_A = 1001
TEAM_B = 1002


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_tenant() -> int:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    db = SessionLocal()
    t = Tenant(name=f"SupScope {stamp}")
    db.add(t)
    db.commit()
    tid = t.id
    db.close()
    return tid


def _make_user(tenant_id: int, role: str, team_id: int | None) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"supscope-{role}-{stamp}@example.com"
    db = SessionLocal()
    u = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        team_id=team_id,
    )
    db.add(u)
    db.commit()
    out = {"email": email, "id": u.id, "tenant_id": tenant_id, "team_id": team_id}
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_device(token: str, priv: Ed25519PrivateKey) -> None:
    pub = _b64(priv.public_key().public_bytes_raw())
    r = httpx.post(
        f"{BASE}/devices/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"public_key": pub, "platform": "android"},
    )
    r.raise_for_status()


def _post_event(token: str, priv: Ed25519PrivateKey) -> str:
    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "type": "check_in",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = _b64(priv.sign(canonical.encode()))
    r = httpx.post(
        f"{BASE}/attendance/events",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "event_id": event_id,
            "event_type": "check_in",
            "payload_b64": _b64(canonical.encode()),
            "signature_b64": signature,
            "previous_hash": None,
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    r.raise_for_status()
    return event_id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _event_for_user(user: dict) -> str:
    token = _login(user["email"])
    priv = Ed25519PrivateKey.generate()
    _register_device(token, priv)
    return _post_event(token, priv)


@pytest.fixture(scope="module")
def fixture_data():
    tenant = _make_tenant()
    other_tenant = _make_tenant()

    sup_a = _make_user(tenant, "supervisor", TEAM_A)
    sup_b = _make_user(tenant, "supervisor", TEAM_B)
    sup_none = _make_user(tenant, "supervisor", None)
    sup_other_tenant = _make_user(other_tenant, "supervisor", TEAM_A)
    emp_a = _make_user(tenant, "employee", TEAM_A)
    emp_b = _make_user(tenant, "employee", TEAM_B)

    emp_a_event = _event_for_user(emp_a)
    emp_b_event = _event_for_user(emp_b)

    return {
        "sup_a_token": _login(sup_a["email"]),
        "sup_b_token": _login(sup_b["email"]),
        "sup_none_token": _login(sup_none["email"]),
        "sup_other_token": _login(sup_other_tenant["email"]),
        "emp_a_token": _login(emp_a["email"]),
        "emp_a_event": emp_a_event,
        "emp_b_event": emp_b_event,
    }


def test_supervisor_sees_only_own_team(fixture_data):
    r = httpx.get(
        f"{BASE}/attendance/team/events",
        headers=_auth(fixture_data["sup_a_token"]),
    )
    assert r.status_code == 200, r.text
    ids = {e["event_id"] for e in r.json()}
    assert fixture_data["emp_a_event"] in ids
    assert fixture_data["emp_b_event"] not in ids


def test_supervisor_b_does_not_see_team_a(fixture_data):
    r = httpx.get(
        f"{BASE}/attendance/team/events",
        headers=_auth(fixture_data["sup_b_token"]),
    )
    assert r.status_code == 200, r.text
    ids = {e["event_id"] for e in r.json()}
    assert fixture_data["emp_b_event"] in ids
    assert fixture_data["emp_a_event"] not in ids


def test_supervisor_without_team_gets_403(fixture_data):
    r = httpx.get(
        f"{BASE}/attendance/team/events",
        headers=_auth(fixture_data["sup_none_token"]),
    )
    assert r.status_code == 403, r.text
    assert "team" in r.json()["detail"].lower()


def test_employee_gets_403(fixture_data):
    r = httpx.get(
        f"{BASE}/attendance/team/events",
        headers=_auth(fixture_data["emp_a_token"]),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Insufficient role"


def test_cross_tenant_supervisor_sees_nothing(fixture_data):
    r = httpx.get(
        f"{BASE}/attendance/team/events",
        headers=_auth(fixture_data["sup_other_token"]),
    )
    assert r.status_code == 200, r.text
    ids = {e["event_id"] for e in r.json()}
    assert fixture_data["emp_a_event"] not in ids
    assert fixture_data["emp_b_event"] not in ids


def test_unauthenticated_gets_401():
    r = httpx.get(f"{BASE}/attendance/team/events")
    assert r.status_code == 401
