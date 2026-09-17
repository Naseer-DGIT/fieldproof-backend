"""IDOR coverage for GET /attendance/team/events/{event_id}.

A supervisor must not be able to distinguish "another team's event" from
"no such event". Both must be 404 with identical bodies.
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
TEAM_A = 2001
TEAM_B = 2002


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_tenant() -> int:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    db = SessionLocal()
    t = Tenant(name=f"SupIDOR {stamp}")
    db.add(t); db.commit()
    tid = t.id; db.close()
    return tid


def _make_user(tenant_id: int, role: str, team_id: int | None) -> dict:
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 10000
    email = f"supidor-{role}-{stamp}@example.com"
    db = SessionLocal()
    u = User(tenant_id=tenant_id, email=email, password_hash=hash_password(PASSWORD),
             role=role, team_id=team_id)
    db.add(u); db.commit()
    out = {"email": email, "id": u.id}
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _register(token: str, priv: Ed25519PrivateKey) -> None:
    pub = _b64(priv.public_key().public_bytes_raw())
    r = httpx.post(f"{BASE}/devices/register",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"public_key": pub, "platform": "android"})
    r.raise_for_status()


def _post(token: str, priv: Ed25519PrivateKey) -> str:
    eid = str(uuid.uuid4())
    payload = {"event_id": eid, "type": "check_in",
               "ts": datetime.now(timezone.utc).isoformat()}
    canon = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = _b64(priv.sign(canon.encode()))
    r = httpx.post(f"{BASE}/attendance/events",
                   headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"},
                   json={"event_id": eid, "event_type": "check_in",
                         "payload_b64": _b64(canon.encode()),
                         "signature_b64": sig, "previous_hash": None,
                         "idempotency_key": str(uuid.uuid4())})
    r.raise_for_status()
    return eid


@pytest.fixture(scope="module")
def data():
    tid = _make_tenant()
    sup_a = _make_user(tid, "supervisor", TEAM_A)
    sup_b = _make_user(tid, "supervisor", TEAM_B)
    emp_a = _make_user(tid, "employee", TEAM_A)

    sup_a_t = _login(sup_a["email"])
    sup_b_t = _login(sup_b["email"])
    emp_a_t = _login(emp_a["email"])

    priv = Ed25519PrivateKey.generate()
    _register(emp_a_t, priv)
    event_a = _post(emp_a_t, priv)

    return {"sup_a_t": sup_a_t, "sup_b_t": sup_b_t, "event_a": event_a}


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_supervisor_reads_own_team_event(data):
    r = httpx.get(f"{BASE}/attendance/team/events/{data['event_a']}",
                  headers=_auth(data["sup_a_t"]))
    assert r.status_code == 200, r.text
    assert r.json()["event_id"] == data["event_a"]


def test_other_team_supervisor_gets_404(data):
    r = httpx.get(f"{BASE}/attendance/team/events/{data['event_a']}",
                  headers=_auth(data["sup_b_t"]))
    assert r.status_code == 404, r.text


def test_nonexistent_event_gets_404(data):
    r = httpx.get(f"{BASE}/attendance/team/events/{uuid.uuid4()}",
                  headers=_auth(data["sup_a_t"]))
    assert r.status_code == 404, r.text


def test_404_bodies_indistinguishable(data):
    r_other = httpx.get(f"{BASE}/attendance/team/events/{data['event_a']}",
                        headers=_auth(data["sup_b_t"]))
    r_missing = httpx.get(f"{BASE}/attendance/team/events/{uuid.uuid4()}",
                          headers=_auth(data["sup_b_t"]))
    assert r_other.status_code == r_missing.status_code == 404
    assert r_other.json() == r_missing.json()
