"""Lab test: BOLA on GET /lab/bola/events/{id}.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
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


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_user(label: str):
    stamp = int(time.time() * 1000) + uuid.uuid4().int % 1000
    email = f"labbola-{label}-{stamp}@example.com"
    db = SessionLocal()
    t = Tenant(name=f"LabBOLA {label} {stamp}")
    db.add(t); db.flush()
    u = User(tenant_id=t.id, email=email,
             password_hash=hash_password(PASSWORD), role="employee")
    db.add(u); db.commit()
    db.close()
    return email


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login",
                   json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _register(token: str, priv: Ed25519PrivateKey) -> None:
    pub = _b64(priv.public_key().public_bytes_raw())
    r = httpx.post(f"{BASE}/devices/register",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"public_key": pub, "platform": "android"})
    r.raise_for_status()


def _post_event(token: str, priv: Ed25519PrivateKey) -> str:
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
def setup():
    tok_a = _login(_make_user("a"))
    tok_b = _login(_make_user("b"))
    priv_a = Ed25519PrivateKey.generate()
    _register(tok_a, priv_a)
    event_a = _post_event(tok_a, priv_a)
    return {"tok_a": tok_a, "tok_b": tok_b, "event_a": event_a}


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_owner_can_read_own_event(setup):
    r = httpx.get(f"{BASE}/lab/bola/events/{setup['event_a']}",
                  headers=_auth(setup["tok_a"]))
    assert r.status_code == 200, r.text
    assert r.json()["event_id"] == setup["event_a"]


def test_other_user_cannot_read_event(setup):
    """After the fix, a foreign event returns 404 (same as a missing one)."""
    r = httpx.get(f"{BASE}/lab/bola/events/{setup['event_a']}",
                  headers=_auth(setup["tok_b"]))
    assert r.status_code == 404, (
        f"expected 404 after the fix, got {r.status_code}. "
        "If this is 200, the vulnerability is still live."
    )


def test_missing_event_returns_404(setup):
    r = httpx.get(f"{BASE}/lab/bola/events/{uuid.uuid4()}",
                  headers=_auth(setup["tok_b"]))
    assert r.status_code == 404
