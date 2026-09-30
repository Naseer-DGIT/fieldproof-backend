"""S7 Day 7 — report endpoint tests."""

import csv
import io
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
    LOPRecord,
    Shift,
    ShiftAssignment,
    Tenant,
    User,
)

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
PASSWORD = "Test1234!"


def _make_tenant(with_shift: bool = True) -> dict:
    stamp = int(_time.time() * 1000)
    db = SessionLocal()
    t = Tenant(name=f"S7 Rep {stamp}")
    db.add(t)
    db.flush()
    hr = User(tenant_id=t.id, email=f"s7-rep-hr-{stamp}@example.com",
              password_hash=hash_password(PASSWORD), role="hr_ops")
    emp = User(tenant_id=t.id, email=f"s7-rep-emp-{stamp}@example.com",
               password_hash=hash_password(PASSWORD), role="employee",
               team_id=10)
    db.add_all([hr, emp])
    db.flush()
    db.commit()

    today = date.today()
    if with_shift:
        shift = Shift(tenant_id=t.id, name=f"Day-{stamp}",
                      start_time="09:00", end_time="18:00",
                      grace_minutes=10, break_minutes=60)
        db.add(shift)
        db.flush()
        db.add(ShiftAssignment(
            tenant_id=t.id, user_id=emp.id, shift_id=shift.id,
            start_date=today, end_date=today + timedelta(days=30),
        ))

        # One check-in / check-out
        dev = Device(user_id=emp.id, public_key=f"rep-dev-{stamp}",
                     attestation_status="PENDING", revoked=False)
        db.add(dev)
        db.flush()
        db.add_all([
            AttendanceEvent(
                event_id=f"rep-in-{stamp}", user_id=emp.id, device_id=dev.id,
                event_type="check_in", payload={}, signature="x",
                previous_event_hash=None,
                idempotency_key=f"rep-in-{stamp}",
                server_received_at=datetime.combine(today, time(9, 5), tzinfo=timezone.utc),
            ),
            AttendanceEvent(
                event_id=f"rep-out-{stamp}", user_id=emp.id, device_id=dev.id,
                event_type="check_out", payload={}, signature="x",
                previous_event_hash=None,
                idempotency_key=f"rep-out-{stamp}",
                server_received_at=datetime.combine(today, time(18, 0), tzinfo=timezone.utc),
            ),
        ])

        # One LOP record
        db.add(LOPRecord(
            tenant_id=t.id, user_id=emp.id, for_date=today,
            days=0.5, source="late_arrival", note="test",
        ))
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


def _today_params(**extra) -> dict:
    today = date.today().isoformat()
    return {"start": today, "end": today, **extra}


# --- Attendance summary -----------------------------------------------------

def test_attendance_summary_json():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params=_today_params(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) >= 1
    assert body[0]["user_id"] == t["emp"]["id"]
    assert body[0]["status"] == "on_time"


def test_attendance_summary_csv():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params=_today_params(format="csv"),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) >= 1
    assert rows[0]["user_id"] == str(t["emp"]["id"])


# --- Work hours -------------------------------------------------------------

def test_work_hours_json():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/work-hours",
        headers=_auth(tok),
        params=_today_params(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["days_with_shift"] == 1
    assert body[0]["worked_minutes"] > 0


def test_work_hours_csv_header():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/work-hours",
        headers=_auth(tok),
        params=_today_params(format="csv"),
    )
    assert r.status_code == 200
    reader = csv.DictReader(io.StringIO(r.text))
    fieldnames = reader.fieldnames or []
    assert "user_id" in fieldnames
    assert "worked_minutes" in fieldnames


# --- Breaks -----------------------------------------------------------------

def test_breaks_report():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/breaks",
        headers=_auth(tok),
        params=_today_params(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert "break_count" in body[0]


# --- LOP --------------------------------------------------------------------

def test_lop_report():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/lop",
        headers=_auth(tok),
        params=_today_params(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["source"] == "late_arrival"


# --- Access control ---------------------------------------------------------

def test_employee_cannot_read_reports():
    t = _make_tenant()
    tok = _login(t["emp"]["email"])
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params=_today_params(),
    )
    assert r.status_code == 403


def test_inverted_range_rejected():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    today = date.today()
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params={
            "start": today.isoformat(),
            "end": (today - timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 422


def test_range_too_long_rejected():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    today = date.today()
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params={
            "start": today.isoformat(),
            "end": (today + timedelta(days=63)).isoformat(),
        },
    )
    assert r.status_code == 422


def test_cross_tenant_report_isolation():
    a = _make_tenant()
    b = _make_tenant()

    tok_a = _login(a["hr"]["email"])
    tok_b = _login(b["hr"]["email"])

    r_a = httpx.get(f"{BASE}/reports/attendance-summary",
                    headers=_auth(tok_a), params=_today_params())
    r_b = httpx.get(f"{BASE}/reports/attendance-summary",
                    headers=_auth(tok_b), params=_today_params())

    assert r_a.status_code == 200
    assert r_b.status_code == 200

    users_a = {row["user_id"] for row in r_a.json()}
    users_b = {row["user_id"] for row in r_b.json()}
    assert a["emp"]["id"] in users_a
    assert b["emp"]["id"] not in users_a
    assert b["emp"]["id"] in users_b
    assert a["emp"]["id"] not in users_b


def test_invalid_format_rejected():
    t = _make_tenant()
    tok = _login(t["hr"]["email"])
    r = httpx.get(
        f"{BASE}/reports/attendance-summary",
        headers=_auth(tok),
        params=_today_params(format="xml"),
    )
    assert r.status_code == 422
