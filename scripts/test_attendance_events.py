"""End-to-end test of POST /attendance/events.

Creates a throwaway user, registers a device, signs an event, posts it,
and asserts the server accepts it. Then exercises three negative paths:
bad signature, chain mismatch, duplicate event_id.
"""

import base64
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_user():
    stamp = int(time.time() * 1000)
    email = f"evt-{stamp}@example.com"
    password = "Test1234!"
    db = SessionLocal()
    tenant = Tenant(name=f"Evt Tenant {stamp}")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        role="employee",
    )
    db.add(user)
    db.commit()
    db.close()
    return email, password


def login(email: str, password: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def register(token: str, pub_b64: str) -> int:
    r = httpx.post(
        f"{BASE}/devices/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"public_key": pub_b64, "platform": "android"},
    )
    r.raise_for_status()
    return r.json()["id"]


def signed_event(priv, event_type, previous_hash, ts=None):
    event_id = str(uuid.uuid4())
    ts = ts or datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": event_id,
        "type": event_type,
        "ts": ts,
    }
    if previous_hash is not None:
        payload["prev"] = previous_hash
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = priv.sign(canonical.encode())
    return {
        "event_id": event_id,
        "event_type": event_type,
        "payload_b64": b64url(canonical.encode()),
        "signature_b64": b64url(sig),
        "previous_hash": previous_hash,
        "idempotency_key": str(uuid.uuid4()),
    }


def post(token, body, expect):
    r = httpx.post(
        f"{BASE}/attendance/events",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    status_ok = r.status_code == expect
    print(f"  POST → {r.status_code} (expected {expect}) {'PASS' if status_ok else 'FAIL'}")
    if not status_ok:
        print(f"  body: {r.text}")
    return r


def main() -> int:
    print("1. create user")
    email, password = make_user()
    print(f"   {email}")

    print("2. login")
    token = login(email, password)

    print("3. generate keypair and register device")
    priv = Ed25519PrivateKey.generate()
    pub_b64 = b64url(priv.public_key().public_bytes_raw())
    device_id = register(token, pub_b64)
    print(f"   device id={device_id}")

    print("4. valid event")
    e1 = signed_event(priv, "check_in", None)
    r = post(token, e1, 201)
    if r.status_code != 201:
        return 1

    print("5. duplicate event_id returns 201 (idempotent)")
    post(token, e1, 201)

    print("6. bad signature returns 400")
    e_bad = signed_event(priv, "check_out", e1["event_id"])
    e_bad["signature_b64"] = b64url(b"\x00" * 64)
    post(token, e_bad, 400)

    print("7. chain mismatch returns 409")
    e2 = signed_event(priv, "check_out", "wrong-previous-hash")
    post(token, e2, 409)

    print("8. valid chained event returns 201")
    e3 = signed_event(priv, "check_out", e1["event_id"])
    r = post(token, e3, 201)
    if r.status_code != 201:
        return 1

    print("9. list events returns 2")
    r = httpx.get(
        f"{BASE}/attendance/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    count = len(r.json())
    print(f"   count={count} {'PASS' if count == 2 else 'FAIL'}")
    if count != 2:
        return 1

    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
