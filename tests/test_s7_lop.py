"""S7 Day 4 — LOP computation tests."""

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
    LeaveRequest,
    LeaveType,
    LOPRecord,
    Shift,
    ShiftAssignment,
    Tenant,
    User,
)
from app.services.lop import compute_for_range  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_pair(role_hr: str = "hr_ops") -> dict:
    """One tenant with an hr_ops user and an employee user."""
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 LOP {stamp}")
    db.add(t)
    db.flush()
    hr = User(tenant_id=t.id, email=f"s7-lop-hr-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role=role_hr)
    emp = User(tenant_id=t.id, email=f"s7-lop-emp-{stamp}@example.com",
               password_hash=hash_password(PASSWORD), role="employee")
    db.add_all([hr, emp])
    db.commit()
    out = {
        "tenant_id": t.id,
        "hr": {"id": hr.id, "email": hr.email},
        "emp": {"id": emp.id, "email": emp.email},
    }
    db.close()
    return out


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _attach_shift(db, tenant_id: int, user_id: int, day: date,
                  name: str = "Day", grace_minutes: int = 10,
                  break_minutes: int = 60) -> Shift:
    shift = Shift(
        tenant_id=tenant_id,
        name=f"{name}-{user_id}",
        start_time="09:00",
        end_time="18:00",
        grace_minutes=grace_minutes,
        break_minutes=break_minutes,
    )
    db.add(shift)
    db.flush()
    db.add(ShiftAssignment(
        tenant_id=tenant_id, user_id=user_id, shift_id=shift.id,
        start_date=day, end_date=day + timedelta(days=30),
    ))
    db.commit()
    return shift


def _attach_device(db, user_id: int) -> Device:
    device = Device(user_id=user_id, public_key=f"dev-lop-{user_id}",
                    attestation_status="PENDING", revoked=False)
    db.add(device)
    db.flush()
    return device


# --- Service-level tests ----------------------------------------------------

def test_absent_produces_one_full_day_lop():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
        counts = compute_for_range(db, pair["tenant_id"], today, today)
        assert counts["inserted"] == 1

        rows = (db.query(LOPRecord)
                .filter(LOPRecord.user_id == pair["emp"]["id"],
                        LOPRecord.for_date == today).all())
        assert len(rows) == 1
        assert rows[0].source == "unapproved_absence"
        assert float(rows[0].days) == 1.0
    finally:
        db.close()


def test_late_produces_half_day_lop():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
        device = _attach_device(db, pair["emp"]["id"])

        checkin = datetime.combine(today, time(9, 20), tzinfo=timezone.utc)
        db.add(AttendanceEvent(
            event_id=f"lop-late-{pair['emp']['id']}",
            user_id=pair["emp"]["id"], device_id=device.id,
            event_type="check_in", payload={}, signature="x",
            previous_event_hash=None,
            idempotency_key=f"lop-late-{pair['emp']['id']}",
            server_received_at=checkin,
        ))
        db.commit()

        counts = compute_for_range(db, pair["tenant_id"], today, today)
        assert counts["inserted"] == 1

        row = (db.query(LOPRecord)
               .filter(LOPRecord.user_id == pair["emp"]["id"],
                       LOPRecord.for_date == today).first())
        assert row.source == "late_arrival"
        assert float(row.days) == 0.5
    finally:
        db.close()


def test_approved_leave_skips_lop():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)

        lt = LeaveType(tenant_id=pair["tenant_id"], name="Casual", is_paid=True)
        db.add(lt)
        db.flush()
        db.add(LeaveRequest(
            tenant_id=pair["tenant_id"], user_id=pair["emp"]["id"],
            leave_type_id=lt.id, start_date=today, end_date=today,
            days=1.0, status="approved",
        ))
        db.commit()

        counts = compute_for_range(db, pair["tenant_id"], today, today)
        assert counts["inserted"] == 0
        assert counts["skipped_leave"] == 1
    finally:
        db.close()


def test_no_shift_skips_user():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        counts = compute_for_range(db, pair["tenant_id"], today, today)
        # Both users have no shift; both are skipped.
        assert counts["inserted"] == 0
        assert counts["skipped_no_shift"] == 2
    finally:
        db.close()


def test_compute_is_idempotent():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)

        first = compute_for_range(db, pair["tenant_id"], today, today)
        assert first["inserted"] == 1

        second = compute_for_range(db, pair["tenant_id"], today, today)
        assert second["inserted"] == 0
        assert second["updated"] == 1

        rows = (db.query(LOPRecord)
                .filter(LOPRecord.user_id == pair["emp"]["id"],
                        LOPRecord.for_date == today).all())
        assert len(rows) == 1
    finally:
        db.close()


# --- API tests --------------------------------------------------------------

def test_hr_ops_can_trigger_compute():
    pair = _make_pair()
    today = date.today()
    tok = _login(pair["hr"]["email"])

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
    finally:
        db.close()

    r = httpx.post(
        f"{BASE}/lop/compute",
        headers=_auth(tok),
        json={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] >= 1


def test_employee_cannot_trigger_compute():
    pair = _make_pair()
    today = date.today()
    tok = _login(pair["emp"]["email"])

    r = httpx.post(
        f"{BASE}/lop/compute",
        headers=_auth(tok),
        json={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 403


def test_compute_rejects_inverted_range():
    pair = _make_pair()
    today = date.today()
    tok = _login(pair["hr"]["email"])

    r = httpx.post(
        f"{BASE}/lop/compute",
        headers=_auth(tok),
        json={"start": today.isoformat(),
              "end": (today - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 422


def test_compute_rejects_range_over_62_days():
    pair = _make_pair()
    today = date.today()
    tok = _login(pair["hr"]["email"])

    r = httpx.post(
        f"{BASE}/lop/compute",
        headers=_auth(tok),
        json={"start": today.isoformat(),
              "end": (today + timedelta(days=63)).isoformat()},
    )
    assert r.status_code == 422


def test_cross_tenant_lop_isolation():
    a = _make_pair()
    b = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, a["tenant_id"], a["emp"]["id"], today)
        _attach_shift(db, b["tenant_id"], b["emp"]["id"], today)
    finally:
        db.close()

    tok_a = _login(a["hr"]["email"])
    httpx.post(f"{BASE}/lop/compute", headers=_auth(tok_a),
               json={"start": today.isoformat(), "end": today.isoformat()})

    r_a = httpx.get(f"{BASE}/lop", headers=_auth(tok_a))
    assert r_a.status_code == 200
    rows = r_a.json()
    assert all(row["tenant_id"] == a["tenant_id"] for row in rows)
