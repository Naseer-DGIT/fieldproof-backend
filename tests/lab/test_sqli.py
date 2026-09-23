"""Lab test: SQL injection.

The test proves the vulnerability exists BEFORE the fix, and proves it
is closed AFTER the fix.

Run only when the lab router is mounted (ENVIRONMENT=lab):

    RUN_LAB_TESTS=1 pytest tests/lab/ -v
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
    reason="lab tests run only with RUN_LAB_TESTS=1 (requires ENVIRONMENT=lab backend)",
)


@pytest.fixture(scope="module")
def seeded():
    """Two tenants, two users. The second must not be visible to a
    search that starts from the first tenant's data."""
    stamp = int(time.time() * 1000)
    db = SessionLocal()
    t1 = Tenant(name=f"Lab A {stamp}")
    t2 = Tenant(name=f"Lab B {stamp}")
    db.add_all([t1, t2])
    db.flush()
    u1 = User(tenant_id=t1.id, email=f"lab-a-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role="employee")
    u2 = User(tenant_id=t2.id, email=f"lab-b-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role="employee")
    db.add_all([u1, u2])
    db.commit()
    out = {"u1_email": u1.email, "u2_email": u2.email}
    db.close()
    return out


def test_normal_search_returns_only_matches(seeded):
    r = httpx.get(f"{BASE}/lab/sqli/search", params={"q": seeded["u1_email"]})
    assert r.status_code == 200
    emails = [row["email"] for row in r.json()["rows"]]
    assert seeded["u1_email"] in emails
    assert seeded["u2_email"] not in emails


def test_sql_injection_leaks_every_row(seeded):
    """The injection returns every user, including the other tenant's.

    BEFORE the fix: this test passes (vulnerability exists).
    AFTER the fix: this test fails, so we rewrite the assertion to
    expect a safe empty or filtered result.
    """
    payload = "%' OR '1'='1"
    r = httpx.get(f"{BASE}/lab/sqli/search", params={"q": payload})
    assert r.status_code == 200
    emails = [row["email"] for row in r.json()["rows"]]

    # FIXED: the injection payload is treated as a literal string.
    # It matches no real email, so the result is empty.
    assert seeded["u1_email"] not in emails
    assert seeded["u2_email"] not in emails
