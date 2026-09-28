"""S7 Day 2 — shift API and policy tests."""

import os
import sys
import time as _time
from datetime import date, datetime, time, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AttendanceEvent,
    Device,
    Shift,
    ShiftAssignment,
    Tenant,
    User,
)
from app.services.shift_policy import classify_day  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_user(role: str) -> dict:
    """One tenant, one user. Used for the API tests where the user is alone."""
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 Shift {stamp} {role}")
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=f"s7-{role}-{stamp}@example.com",
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    db.add(u)
    db.commit()
    out = {"email": u.email, "id": u.id, "tenant_id": t.id}
    db.close()
    return out


def _make_pair() -> dict:
    """One tenant with an hr_ops user and an employee user.

    Required for the policy tests: the assignment is created under the
    tenant, and the employee must belong to that same tenant for the
    lookup in classify_day to find it.
    """
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 Pair {stamp}")
    db.add(t)
    db.flush()
    hr = User(
        tenant_id=t.id,
        email=f"s7-pair-hr-{stamp}@example.com",
        password_hash=hash_password(PASSWORD),
        role="hr_ops",
    )
    emp = User(
        tenant_id=t.id,
        email=f"s7-pair-emp-{stamp}@example.com",
        password_hash=hash_password(PASSWORD),
        role="employee",
    )
    db.add_all([hr, emp])
    db.commit()
    out = {
        "tenant_id": t.id,
        "hr": {"email": hr.email, "id": hr.id, "tenant_id": t.id},
        "emp": {"email": emp.email, "id": emp.id, "tenant_id": t.id},
    }
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(
        f"{BASE}/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


# --- API tests --------------------------------------------------------------

def test_hr_ops_can_create_shift():
    u = _make_user("hr_ops")
    tok = _login(u["email"])
    r = httpx.post(
        f"{BASE}/shifts",
        headers=_auth(tok),
        json={
            "name": "Day",
            "start_time": "09:00",
            "end_time": "18:00",
            "grace_minutes": 10,
            "break_minutes": 60,
            "overtime_threshold_minutes": 30,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Day"


def test_employee_cannot_create_shift():
    u = _make_user("employee")
    tok = _login(u["email"])
    r = httpx.post(
        f"{BASE}/shifts",
        headers=_auth(tok),
        json={
            "name": "X",
            "start_time": "09:00",
            "end_time": "18:00",
            "grace_minutes": 0,
            "break_minutes": 0,
            "overtime_threshold_minutes": 0,
        },
    )
    assert r.status_code == 403


def test_duplicate_shift_name_conflicts():
    u = _make_user("hr_ops")
    tok = _login(u["email"])
    body = {
        "name": "Day",
        "start_time": "09:00",
        "end_time": "18:00",
        "grace_minutes": 0,
        "break_minutes": 0,
        "overtime_threshold_minutes": 0,
    }
    assert httpx.post(f"{BASE}/shifts", headers=_auth(tok), json=body).status_code == 201
    r = httpx.post(f"{BASE}/shifts", headers=_auth(tok), json=body)
    assert r.status_code == 409


def test_cross_tenant_shift_isolation():
    a = _make_user("hr_ops")
    b = _make_user("hr_ops")

    tok_a = _login(a["email"])
    tok_b = _login(b["email"])

    body = {
        "name": "Day",
        "start_time": "09:00",
        "end_time": "18:00",
        "grace_minutes": 0,
        "break_minutes": 0,
        "overtime_threshold_minutes": 0,
    }
    assert httpx.post(f"{BASE}/shifts", headers=_auth(tok_a), json=body).status_code == 201
    assert httpx.post(f"{BASE}/shifts", headers=_auth(tok_b), json=body).status_code == 201

    r_a = httpx.get(f"{BASE}/shifts", headers=_auth(tok_a))
    r_b = httpx.get(f"{BASE}/shifts", headers=_auth(tok_b))

    assert len(r_a.json()) == 1
    assert len(r_b.json()) == 1
    assert r_a.json()[0]["tenant_id"] != r_b.json()[0]["tenant_id"]


# --- Policy tests -----------------------------------------------------------

def test_policy_returns_no_shift_when_unassigned():
    u = _make_user("employee")
    db = SessionLocal()
    try:
        user = db.get(User, u["id"])
        result = classify_day(db, user, date.today())
        assert result["status"] == "no_shift", result
    finally:
        db.close()


def test_policy_marks_late_when_checkin_after_grace():
    pair = _make_pair()

    db = SessionLocal()
    try:
        emp_user = db.get(User, pair["emp"]["id"])

        shift = Shift(
            tenant_id=pair["tenant_id"],
            name=f"Day-late-{emp_user.id}",
            start_time="09:00",
            end_time="18:00",
            grace_minutes=10,
            break_minutes=60,
        )
        db.add(shift)
        db.flush()

        today = date.today()
        db.add(ShiftAssignment(
            tenant_id=pair["tenant_id"],
            user_id=emp_user.id,
            shift_id=shift.id,
            start_date=today,
            end_date=today + timedelta(days=7),
        ))
        db.commit()

        device = Device(
            user_id=emp_user.id,
            public_key=f"test-key-late-{emp_user.id}",
            attestation_status="PENDING",
            revoked=False,
        )
        db.add(device)
        db.flush()

        checkin_time = datetime.combine(today, time(9, 20), tzinfo=timezone.utc)
        db.add(AttendanceEvent(
            event_id=f"evt-late-{emp_user.id}",
            user_id=emp_user.id,
            device_id=device.id,
            event_type="check_in",
            payload={},
            signature="x",
            previous_event_hash=None,
            idempotency_key=f"policy-late-{emp_user.id}",
            server_received_at=checkin_time,
        ))
        db.commit()

        result = classify_day(db, emp_user, today)
        assert result["status"] == "late", result
        assert result["minutes_late"] == 10, result
    finally:
        db.close()


def test_policy_marks_on_time_within_grace():
    pair = _make_pair()

    db = SessionLocal()
    try:
        emp_user = db.get(User, pair["emp"]["id"])

        shift = Shift(
            tenant_id=pair["tenant_id"],
            name=f"Day-ontime-{emp_user.id}",
            start_time="09:00",
            end_time="18:00",
            grace_minutes=10,
            break_minutes=60,
        )
        db.add(shift)
        db.flush()

        today = date.today()
        db.add(ShiftAssignment(
            tenant_id=pair["tenant_id"],
            user_id=emp_user.id,
            shift_id=shift.id,
            start_date=today,
            end_date=today + timedelta(days=7),
        ))
        db.commit()

        device = Device(
            user_id=emp_user.id,
            public_key=f"test-key-ontime-{emp_user.id}",
            attestation_status="PENDING",
            revoked=False,
        )
        db.add(device)
        db.flush()

        checkin_time = datetime.combine(today, time(9, 5), tzinfo=timezone.utc)
        checkout_time = datetime.combine(today, time(18, 0), tzinfo=timezone.utc)
        db.add_all([
            AttendanceEvent(
                event_id=f"evt-ontime-in-{emp_user.id}",
                user_id=emp_user.id,
                device_id=device.id,
                event_type="check_in",
                payload={},
                signature="x",
                previous_event_hash=None,
                idempotency_key=f"policy-ontime-in-{emp_user.id}",
                server_received_at=checkin_time,
            ),
            AttendanceEvent(
                event_id=f"evt-ontime-out-{emp_user.id}",
                user_id=emp_user.id,
                device_id=device.id,
                event_type="check_out",
                payload={},
                signature="x",
                previous_event_hash=None,
                idempotency_key=f"policy-ontime-out-{emp_user.id}",
                server_received_at=checkout_time,
            ),
        ])
        db.commit()

        result = classify_day(db, emp_user, today)
        assert result["status"] == "on_time", result
    finally:
        db.close()


def test_policy_marks_absent_without_checkin():
    pair = _make_pair()

    db = SessionLocal()
    try:
        emp_user = db.get(User, pair["emp"]["id"])

        shift = Shift(
            tenant_id=pair["tenant_id"],
            name=f"Day-absent-{emp_user.id}",
            start_time="09:00",
            end_time="18:00",
            grace_minutes=0,
            break_minutes=0,
        )
        db.add(shift)
        db.flush()

        today = date.today()
        db.add(ShiftAssignment(
            tenant_id=pair["tenant_id"],
            user_id=emp_user.id,
            shift_id=shift.id,
            start_date=today,
            end_date=today + timedelta(days=7),
        ))
        db.commit()

        result = classify_day(db, emp_user, today)
        assert result["status"] == "absent", result
    finally:
        db.close()
