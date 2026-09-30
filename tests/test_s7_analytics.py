"""S7 Day 5 — analytics aggregation tests."""

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
from app.services.analytics import day_summary, summary_for_range  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_pair(role_hr: str = "hr_ops") -> dict:
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 An {stamp}")
    db.add(t)
    db.flush()
    hr = User(tenant_id=t.id, email=f"s7-an-hr-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role=role_hr)
    emp = User(tenant_id=t.id, email=f"s7-an-emp-{stamp}@example.com",
               password_hash=hash_password(PASSWORD), role="employee",
               team_id=10)
    db.add_all([hr, emp])
    db.commit()
    out = {
        "tenant_id": t.id,
        "hr": {"id": hr.id, "email": hr.email},
        "emp": {"id": emp.id, "email": emp.email},
    }
    db.close()
    return out


def _attach_shift(db, tenant_id: int, user_id: int, day: date,
                  shift_name: str | None = None,
                  start: str = "09:00", end: str = "18:00",
                  grace: int = 10, break_min: int = 60,
                  overtime: int = 30) -> Shift:
    shift = Shift(
        tenant_id=tenant_id,
        name=shift_name or f"Day-{user_id}",
        start_time=start, end_time=end,
        grace_minutes=grace, break_minutes=break_min,
        overtime_threshold_minutes=overtime,
    )
    db.add(shift)
    db.flush()
    db.add(ShiftAssignment(
        tenant_id=tenant_id, user_id=user_id, shift_id=shift.id,
        start_date=day, end_date=day + timedelta(days=30),
    ))
    db.commit()
    return shift


def _device(db, user_id: int) -> Device:
    d = Device(user_id=user_id, public_key=f"an-dev-{user_id}",
               attestation_status="PENDING", revoked=False)
    db.add(d)
    db.flush()
    return d


def _login(email: str) -> str:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _add_event(db, user_id: int, device_id: int, kind: str,
               when: datetime, suffix: str) -> None:
    db.add(AttendanceEvent(
        event_id=f"an-{kind}-{suffix}",
        user_id=user_id, device_id=device_id,
        event_type=kind, payload={}, signature="x",
        previous_event_hash=None,
        idempotency_key=f"an-{kind}-{suffix}",
        server_received_at=when,
    ))


# --- Service tests ----------------------------------------------------------

def test_no_shift_returns_none():
    pair = _make_pair()
    db = SessionLocal()
    try:
        user = db.get(User, pair["emp"]["id"])
        assert day_summary(db, user, date.today()) is None
    finally:
        db.close()


def test_full_day_work_hours():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
        dev = _device(db, pair["emp"]["id"])

        _add_event(db, pair["emp"]["id"], dev.id, "check_in",
                   datetime.combine(today, time(9, 0), tzinfo=timezone.utc),
                   f"fh-in-{pair['emp']['id']}")
        _add_event(db, pair["emp"]["id"], dev.id, "check_out",
                   datetime.combine(today, time(18, 0), tzinfo=timezone.utc),
                   f"fh-out-{pair['emp']['id']}")
        db.commit()

        user = db.get(User, pair["emp"]["id"])
        row = day_summary(db, user, today)
        assert row is not None
        assert row["scheduled_minutes"] == 480  # 09:00-18:00 minus 60
        assert row["worked_minutes"] == 540     # 09:00-18:00 with no break recorded
        assert row["status"] == "on_time"
    finally:
        db.close()


def test_break_analysis():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
        dev = _device(db, pair["emp"]["id"])

        # Check-in, break start, break end, check-out
        _add_event(db, pair["emp"]["id"], dev.id, "check_in",
                   datetime.combine(today, time(9, 0), tzinfo=timezone.utc),
                   f"br-in-{pair['emp']['id']}")
        _add_event(db, pair["emp"]["id"], dev.id, "break_start",
                   datetime.combine(today, time(13, 0), tzinfo=timezone.utc),
                   f"br-bs-{pair['emp']['id']}")
        _add_event(db, pair["emp"]["id"], dev.id, "break_end",
                   datetime.combine(today, time(13, 45), tzinfo=timezone.utc),
                   f"br-be-{pair['emp']['id']}")
        _add_event(db, pair["emp"]["id"], dev.id, "check_out",
                   datetime.combine(today, time(18, 0), tzinfo=timezone.utc),
                   f"br-out-{pair['emp']['id']}")
        db.commit()

        user = db.get(User, pair["emp"]["id"])
        row = day_summary(db, user, today)
        assert row["break_count"] == 1
        assert row["total_break_minutes"] == 45
        assert row["longest_break_minutes"] == 45
        # Worked is check-out minus check-in minus recorded breaks
        assert row["worked_minutes"] == (540 - 45)
    finally:
        db.close()


def test_punctuality_and_overtime():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today,
                      grace=5, overtime=15)
        dev = _device(db, pair["emp"]["id"])

        # Check-in at 09:15 (10 minutes late after 5-minute grace)
        # Check-out at 18:30 (15 minutes overtime after 15-minute threshold)
        _add_event(db, pair["emp"]["id"], dev.id, "check_in",
                   datetime.combine(today, time(9, 15), tzinfo=timezone.utc),
                   f"po-in-{pair['emp']['id']}")
        _add_event(db, pair["emp"]["id"], dev.id, "check_out",
                   datetime.combine(today, time(18, 30), tzinfo=timezone.utc),
                   f"po-out-{pair['emp']['id']}")
        db.commit()

        user = db.get(User, pair["emp"]["id"])
        row = day_summary(db, user, today)
        assert row["minutes_late"] == 10
        assert row["overtime_minutes"] == 15
        assert row["status"] == "late"
    finally:
        db.close()


def test_summary_for_range_multiple_days():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
        user = db.get(User, pair["emp"]["id"])
        rows = summary_for_range(db, user, today, today + timedelta(days=4))
        # 5 days in the range, all with the same shift assignment
        assert len(rows) == 5
    finally:
        db.close()


# --- API tests --------------------------------------------------------------

def test_analytics_me_returns_own_days():
    pair = _make_pair()
    today = date.today()

    db = SessionLocal()
    try:
        _attach_shift(db, pair["tenant_id"], pair["emp"]["id"], today)
    finally:
        db.close()

    tok = _login(pair["emp"]["email"])
    r = httpx.get(
        f"{BASE}/analytics/me",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == pair["emp"]["id"]
    assert len(body["days"]) == 1


def test_analytics_me_rejects_inverted_range():
    pair = _make_pair()
    tok = _login(pair["emp"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/me",
        headers=_auth(tok),
        params={"start": today.isoformat(),
                "end": (today - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 422


def test_analytics_me_rejects_long_range():
    pair = _make_pair()
    tok = _login(pair["emp"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/me",
        headers=_auth(tok),
        params={"start": today.isoformat(),
                "end": (today + timedelta(days=63)).isoformat()},
    )
    assert r.status_code == 422


def test_employee_cannot_read_other_user_analytics():
    pair = _make_pair()
    tok = _login(pair["emp"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/users/{pair['hr']['id']}",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 403


def test_hr_can_read_any_user_in_tenant():
    pair = _make_pair()
    tok = _login(pair["hr"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/users/{pair['emp']['id']}",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == pair["emp"]["id"]


def test_cross_tenant_user_analytics_returns_404():
    a = _make_pair()
    b = _make_pair()
    today = date.today()

    tok_a = _login(a["hr"]["email"])
    r = httpx.get(
        f"{BASE}/analytics/users/{b['emp']['id']}",
        headers=_auth(tok_a),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 404


def test_supervisor_cannot_read_other_team_analytics():
    """Supervisor in team 10 queries a user in team 20."""
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    try:
        t = Tenant(name=f"S7 An Team {stamp}")
        db.add(t)
        db.flush()
        sup = User(tenant_id=t.id, email=f"s7-an-sup-{stamp}@example.com",
                   password_hash=hash_password(PASSWORD),
                   role="supervisor", team_id=10)
        other = User(tenant_id=t.id, email=f"s7-an-other-{stamp}@example.com",
                     password_hash=hash_password(PASSWORD),
                     role="employee", team_id=20)
        db.add_all([sup, other])
        db.commit()
        sup_email = sup.email
        other_id = other.id
        tenant_id = t.id
    finally:
        db.close()

    tok = _login(sup_email)
    today = date.today()
    r = httpx.get(
        f"{BASE}/analytics/users/{other_id}",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 404
