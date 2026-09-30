"""S7 Day 6 — tenant-wide analytics tests."""

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
    Shift,
    ShiftAssignment,
    Tenant,
    User,
)
from app.services.analytics import by_shift, by_team, tenant_rollup  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_tenant(team_ids: list[int | None], hr_role: str = "hr_ops") -> dict:
    """One tenant with one hr user and one employee per team id."""
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 AnT {stamp}")
    db.add(t)
    db.flush()
    hr = User(tenant_id=t.id, email=f"s7-ant-hr-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role=hr_role)
    db.add(hr)
    db.flush()
    emps = []
    for i, team_id in enumerate(team_ids):
        emp = User(tenant_id=t.id,
                   email=f"s7-ant-e{i}-{stamp}@example.com",
                   password_hash=hash_password(PASSWORD),
                   role="employee", team_id=team_id)
        db.add(emp)
        db.flush()
        emps.append({"id": emp.id, "email": emp.email, "team_id": team_id})
    db.commit()
    out = {
        "tenant_id": t.id,
        "hr": {"id": hr.id, "email": hr.email},
        "employees": emps,
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
                  name: str = "Day", grace: int = 10,
                  start: str = "09:00", end: str = "18:00") -> Shift:
    shift = Shift(
        tenant_id=tenant_id, name=f"{name}-{user_id}",
        start_time=start, end_time=end,
        grace_minutes=grace, break_minutes=60,
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
    d = Device(user_id=user_id, public_key=f"ant-dev-{user_id}",
               attestation_status="PENDING", revoked=False)
    db.add(d)
    db.flush()
    return d


def _event(db, user_id: int, device_id: int, kind: str,
           when: datetime, tag: str) -> None:
    db.add(AttendanceEvent(
        event_id=f"ant-{kind}-{tag}",
        user_id=user_id, device_id=device_id,
        event_type=kind, payload={}, signature="x",
        previous_event_hash=None,
        idempotency_key=f"ant-{kind}-{tag}",
        server_received_at=when,
    ))


# --- Service tests ----------------------------------------------------------

def test_tenant_rollup_empty_tenant():
    t = _make_tenant([])
    db = SessionLocal()
    try:
        result = tenant_rollup(db, t["tenant_id"], date.today(), date.today())
        # Only the hr user, no shifts
        assert result["days_with_shift"] == 0
        assert result["attendance_rate"] == 0.0
        assert result["user_count"] >= 1
    finally:
        db.close()


def test_tenant_rollup_with_attendance_and_absence():
    t = _make_tenant([10, 10])
    today = date.today()
    db = SessionLocal()
    try:
        # Employee 0: full day
        _attach_shift(db, t["tenant_id"], t["employees"][0]["id"], today)
        dev = _device(db, t["employees"][0]["id"])
        _event(db, t["employees"][0]["id"], dev.id, "check_in",
               datetime.combine(today, time(9, 0), tzinfo=timezone.utc),
               f"tenant-a-{t['employees'][0]['id']}")
        _event(db, t["employees"][0]["id"], dev.id, "check_out",
               datetime.combine(today, time(18, 0), tzinfo=timezone.utc),
               f"tenant-b-{t['employees'][0]['id']}")
        # Employee 1: assigned but no events → absent
        _attach_shift(db, t["tenant_id"], t["employees"][1]["id"], today)
        db.commit()

        result = tenant_rollup(db, t["tenant_id"], today, today)
        # Both employees have a shift, so 2 days in the denominator.
        assert result["days_with_shift"] == 2
        assert result["days_present"] == 1
        assert result["days_absent"] == 1
        assert result["attendance_rate"] == 0.5
    finally:
        db.close()


def test_tenant_rollup_counts_leave_in_rate():
    t = _make_tenant([10])
    today = date.today()
    db = SessionLocal()
    try:
        _attach_shift(db, t["tenant_id"], t["employees"][0]["id"], today)

        lt = LeaveType(tenant_id=t["tenant_id"], name="Casual", is_paid=True)
        db.add(lt)
        db.flush()
        db.add(LeaveRequest(
            tenant_id=t["tenant_id"], user_id=t["employees"][0]["id"],
            leave_type_id=lt.id, start_date=today, end_date=today,
            days=1.0, status="approved",
        ))
        db.commit()

        result = tenant_rollup(db, t["tenant_id"], today, today)
        assert result["days_with_shift"] == 1
        assert result["days_on_leave"] == 1
        assert result["days_present"] == 0
        assert result["attendance_rate"] == 1.0
    finally:
        db.close()


def test_by_shift_groups_correctly():
    t = _make_tenant([10, 10])
    today = date.today()
    db = SessionLocal()
    try:
        _attach_shift(db, t["tenant_id"], t["employees"][0]["id"], today, name="Day")
        _attach_shift(db, t["tenant_id"], t["employees"][1]["id"], today, name="Night",
                      start="21:00", end="06:00")
        db.commit()

        rows = by_shift(db, t["tenant_id"], today, today)
        names = sorted(r["shift_name"].split("-")[0] for r in rows)
        assert names == ["Day", "Night"]
    finally:
        db.close()


def test_by_team_groups_correctly():
    t = _make_tenant([10, 10, 20])
    today = date.today()
    db = SessionLocal()
    try:
        for emp in t["employees"]:
            _attach_shift(db, t["tenant_id"], emp["id"], today)
        db.commit()

        rows = by_team(db, t["tenant_id"], today, today)
        by_id = {r["team_id"]: r for r in rows}
        assert by_id[10]["user_count"] == 2
        assert by_id[20]["user_count"] == 1
    finally:
        db.close()


def test_by_team_groups_unassigned():
    t = _make_tenant([None, None])
    today = date.today()
    db = SessionLocal()
    try:
        for emp in t["employees"]:
            _attach_shift(db, t["tenant_id"], emp["id"], today)
        db.commit()

        rows = by_team(db, t["tenant_id"], today, today)
        unassigned = [r for r in rows if r["team_id"] is None]
        assert len(unassigned) == 1
        # The two employees plus the hr_ops user, who has no team either.
        assert unassigned[0]["user_count"] == 3
    finally:
        db.close()


# --- API tests --------------------------------------------------------------

def test_hr_can_read_tenant_rollup():
    t = _make_tenant([10])
    today = date.today()
    db = SessionLocal()
    try:
        _attach_shift(db, t["tenant_id"], t["employees"][0]["id"], today)
    finally:
        db.close()

    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/analytics/tenant",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200, r.text
    assert "attendance_rate" in r.json()


def test_employee_cannot_read_tenant_rollup():
    t = _make_tenant([10])
    tok = _login(t["employees"][0]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/tenant",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 403


def test_supervisor_cannot_read_tenant_rollup():
    """A supervisor uses /analytics/users/{id}, not /analytics/tenant."""
    t = _make_tenant([10], hr_role="supervisor")
    tok = _login(t["hr"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/tenant",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 403


def test_tenant_rollup_rejects_long_range():
    t = _make_tenant([10])
    tok = _login(t["hr"]["email"])
    today = date.today()

    r = httpx.get(
        f"{BASE}/analytics/tenant",
        headers=_auth(tok),
        params={"start": today.isoformat(),
                "end": (today + timedelta(days=63)).isoformat()},
    )
    assert r.status_code == 422


def test_by_shift_endpoint():
    t = _make_tenant([10])
    today = date.today()
    db = SessionLocal()
    try:
        _attach_shift(db, t["tenant_id"], t["employees"][0]["id"], today)
    finally:
        db.close()

    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/analytics/by-shift",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_by_team_endpoint():
    t = _make_tenant([10, 20])
    today = date.today()
    db = SessionLocal()
    try:
        for emp in t["employees"]:
            _attach_shift(db, t["tenant_id"], emp["id"], today)
    finally:
        db.close()

    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/analytics/by-team",
        headers=_auth(tok),
        params={"start": today.isoformat(), "end": today.isoformat()},
    )
    assert r.status_code == 200
    rows = r.json()
    team_ids = [row["team_id"] for row in rows]
    assert 10 in team_ids
    assert 20 in team_ids
