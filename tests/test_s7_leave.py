"""S7 Day 3 — leave types, requests, approval flow tests."""

import os
import sys
import time as _time
from datetime import date, timedelta

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import LeaveRequest, LeaveType, Tenant, User  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_tenant_with_users(*roles: str) -> dict:
    """One tenant, one user per role. Returns the credentials."""
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 Leave {stamp}")
    db.add(t)
    db.flush()
    users = {}
    for role in roles:
        u = User(
            tenant_id=t.id,
            email=f"s7-leave-{role}-{stamp}@example.com",
            password_hash=hash_password(PASSWORD),
            role=role,
        )
        db.add(u)
        db.flush()
        users[role] = {"id": u.id, "email": u.email}
    db.commit()
    out = {"tenant_id": t.id, "users": users}
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _create_type(token: str, name: str = "Casual") -> int:
    r = httpx.post(
        f"{BASE}/leave/types",
        headers=_auth(token),
        json={"name": name, "is_paid": True, "annual_entitlement_days": 12},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tomorrow() -> date:
    return date.today() + timedelta(days=1)


# --- Leave types ------------------------------------------------------------

def test_hr_ops_can_create_leave_type():
    pair = _make_tenant_with_users("hr_ops")
    tok = _login(pair["users"]["hr_ops"]["email"])
    lt_id = _create_type(tok)
    assert lt_id > 0


def test_employee_cannot_create_leave_type():
    pair = _make_tenant_with_users("employee")
    tok = _login(pair["users"]["employee"]["email"])
    r = httpx.post(
        f"{BASE}/leave/types",
        headers=_auth(tok),
        json={"name": "X", "is_paid": True},
    )
    assert r.status_code == 403


def test_duplicate_leave_type_conflicts():
    pair = _make_tenant_with_users("hr_ops")
    tok = _login(pair["users"]["hr_ops"]["email"])
    _create_type(tok)
    r = httpx.post(
        f"{BASE}/leave/types",
        headers=_auth(tok),
        json={"name": "Casual", "is_paid": True},
    )
    assert r.status_code == 409


def test_cross_tenant_leave_types_isolated():
    a = _make_tenant_with_users("hr_ops")
    b = _make_tenant_with_users("hr_ops")
    tok_a = _login(a["users"]["hr_ops"]["email"])
    tok_b = _login(b["users"]["hr_ops"]["email"])

    _create_type(tok_a, "A-Casual")
    _create_type(tok_b, "B-Casual")

    r_a = httpx.get(f"{BASE}/leave/types", headers=_auth(tok_a))
    r_b = httpx.get(f"{BASE}/leave/types", headers=_auth(tok_b))

    assert [x["name"] for x in r_a.json()] == ["A-Casual"]
    assert [x["name"] for x in r_b.json()] == ["B-Casual"]


# --- Leave requests ---------------------------------------------------------

def test_employee_can_request_leave():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    r = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={
            "leave_type_id": lt_id,
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
            "days": 1.0,
            "reason": "Test",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["user_id"] == pair["users"]["employee"]["id"]


def test_past_date_is_rejected():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    yesterday = date.today() - timedelta(days=1)
    r = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={
            "leave_type_id": lt_id,
            "start_date": yesterday.isoformat(),
            "end_date": yesterday.isoformat(),
            "days": 1.0,
        },
    )
    assert r.status_code == 422
    assert "past" in r.json()["detail"].lower()


def test_overlapping_request_is_rejected():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    end = start + timedelta(days=2)
    body = {
        "leave_type_id": lt_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": 3.0,
    }
    assert httpx.post(f"{BASE}/leave/requests", headers=_auth(emp_tok), json=body).status_code == 201
    r = httpx.post(f"{BASE}/leave/requests", headers=_auth(emp_tok), json=body)
    assert r.status_code == 422
    assert "overlap" in r.json()["detail"].lower()


def test_employee_sees_only_their_own_requests():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    )

    r = httpx.get(f"{BASE}/leave/requests", headers=_auth(emp_tok))
    assert len(r.json()) == 1
    assert r.json()[0]["user_id"] == pair["users"]["employee"]["id"]


def test_manager_sees_tenant_requests():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    )

    r = httpx.get(f"{BASE}/leave/requests", headers=_auth(hr_tok))
    assert len(r.json()) >= 1


# --- Decisions --------------------------------------------------------------

def test_supervisor_can_approve():
    pair = _make_tenant_with_users("hr_ops", "employee", "supervisor")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    sup_tok = _login(pair["users"]["supervisor"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    created = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    ).json()

    r = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/decision",
        headers=_auth(sup_tok),
        json={"decision": "approved", "note": "ok"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_employee_cannot_decide():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    created = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    ).json()

    r = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/decision",
        headers=_auth(emp_tok),
        json={"decision": "approved"},
    )
    assert r.status_code == 403


def test_decided_request_cannot_be_redecided():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    created = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    ).json()

    first = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/decision",
        headers=_auth(hr_tok),
        json={"decision": "approved"},
    )
    assert first.status_code == 200

    second = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/decision",
        headers=_auth(hr_tok),
        json={"decision": "rejected"},
    )
    assert second.status_code == 409


def test_employee_can_cancel_own_pending():
    pair = _make_tenant_with_users("hr_ops", "employee")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])
    emp_tok = _login(pair["users"]["employee"]["email"])
    lt_id = _create_type(hr_tok)

    start = _tomorrow()
    created = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    ).json()

    r = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/cancel",
        headers=_auth(emp_tok),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cross_tenant_decision_returns_404():
    a = _make_tenant_with_users("hr_ops", "employee")
    b = _make_tenant_with_users("hr_ops")

    hr_a_tok = _login(a["users"]["hr_ops"]["email"])
    emp_a_tok = _login(a["users"]["employee"]["email"])
    hr_b_tok = _login(b["users"]["hr_ops"]["email"])

    lt_id = _create_type(hr_a_tok)
    start = _tomorrow()
    created = httpx.post(
        f"{BASE}/leave/requests",
        headers=_auth(emp_a_tok),
        json={"leave_type_id": lt_id, "start_date": start.isoformat(),
              "end_date": start.isoformat(), "days": 1.0},
    ).json()

    # HR in tenant B tries to approve a request in tenant A.
    r = httpx.post(
        f"{BASE}/leave/requests/{created['id']}/decision",
        headers=_auth(hr_b_tok),
        json={"decision": "approved"},
    )
    assert r.status_code == 404


def test_decision_on_missing_request_returns_404():
    pair = _make_tenant_with_users("hr_ops")
    hr_tok = _login(pair["users"]["hr_ops"]["email"])

    r = httpx.post(
        f"{BASE}/leave/requests/99999999/decision",
        headers=_auth(hr_tok),
        json={"decision": "approved"},
    )
    assert r.status_code == 404
