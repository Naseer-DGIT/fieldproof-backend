"""IDOR coverage for GET /attendance/events/{event_id}.

Each test creates two users in the same tenant, each with one event,
then tries to read the other's event. The correct response is 404 for
both "not yours" and "does not exist", with identical bodies.
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


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_tenant() -> int:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    db = SessionLocal()
    tenant = Tenant(name=f"IDOR Tenant {stamp}")
    db.add(tenant)
    db.commit()
    tid = tenant.id
    db.close()
    return tid


def _make_user(tenant_id: int) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"idor-{stamp}@example.com"
    db = SessionLocal()
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(PASSWORD),
        role="employee",
    )
    db.add(user)
    db.commit()
    out = {"email": email, "user_id": user.id, "tenant_id": tenant_id}
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


@pytest.fixture(scope="module")
def users_with_events():
    tid = _make_tenant()
    a = _make_user(tid)
    b = _make_user(tid)
    tok_a = _login(a["email"])
    tok_b = _login(b["email"])
    priv_a = Ed25519PrivateKey.generate()
    priv_b = Ed25519PrivateKey.generate()
    _register_device(tok_a, priv_a)
    _register_device(tok_b, priv_b)
    event_a = _post_event(tok_a, priv_a)
    event_b = _post_event(tok_b, priv_b)
    return {
        "a": {"token": tok_a, "event": event_a},
        "b": {"token": tok_b, "event": event_b},
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_read_own_event(users_with_events):
    a = users_with_events["a"]
    r = httpx.get(
        f"{BASE}/attendance/events/{a['event']}",
        headers=_auth(a["token"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["event_id"] == a["event"]


def test_other_user_same_tenant_gets_404(users_with_events):
    a = users_with_events["a"]
    b = users_with_events["b"]
    r = httpx.get(
        f"{BASE}/attendance/events/{a['event']}",
        headers=_auth(b["token"]),
    )
    assert r.status_code == 404, r.text


def test_nonexistent_event_gets_404(users_with_events):
    b = users_with_events["b"]
    r = httpx.get(
        f"{BASE}/attendance/events/{uuid.uuid4()}",
        headers=_auth(b["token"]),
    )
    assert r.status_code == 404, r.text


def test_404_bodies_are_indistinguishable(users_with_events):
    """The critical test. An attacker comparing "not yours" to "does not
    exist" must see the exact same response."""
    a = users_with_events["a"]
    b = users_with_events["b"]

    r_not_mine = httpx.get(
        f"{BASE}/attendance/events/{a['event']}",
        headers=_auth(b["token"]),
    )
    r_missing = httpx.get(
        f"{BASE}/attendance/events/{uuid.uuid4()}",
        headers=_auth(b["token"]),
    )

    assert r_not_mine.status_code == r_missing.status_code == 404
    assert r_not_mine.json() == r_missing.json()
    assert r_not_mine.headers.get("content-type") == r_missing.headers.get(
        "content-type"
    )


def test_cross_tenant_also_gets_404():
    tid_a = _make_tenant()
    tid_b = _make_tenant()
    a = _make_user(tid_a)
    b = _make_user(tid_b)
    tok_a = _login(a["email"])
    tok_b = _login(b["email"])
    priv_a = Ed25519PrivateKey.generate()
    priv_b = Ed25519PrivateKey.generate()
    _register_device(tok_a, priv_a)
    _register_device(tok_b, priv_b)
    event_a = _post_event(tok_a, priv_a)

    r = httpx.get(
        f"{BASE}/attendance/events/{event_a}",
        headers=_auth(tok_b),
    )
    assert r.status_code == 404


def test_unauthenticated_gets_401(users_with_events):
    a = users_with_events["a"]
    r = httpx.get(f"{BASE}/attendance/events/{a['event']}")
    assert r.status_code == 401
