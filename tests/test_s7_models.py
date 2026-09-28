"""Tests for the S7 shift and leave models.

These tests exercise the schema and the tenant-scoped helpers. They do
not test HTTP endpoints — those arrive on later days.
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.tenant import (  # noqa: E402
    leave_requests_for_self,
    leave_types_for_tenant,
    lop_records_for_self,
    shift_assignments_for_self,
    shifts_for_tenant,
)
from app.models import (  # noqa: E402
    LeaveRequest,
    LeaveType,
    LOPRecord,
    Shift,
    ShiftAssignment,
    Tenant,
    User,
)


@pytest.fixture
def two_tenants():
    """Two tenants, each with one user. Cleaned up after the test."""
    stamp = int(date.today().strftime("%Y%m%d%H%M%S"))
    db = SessionLocal()
    try:
        t1 = Tenant(name=f"S7 A {stamp}")
        t2 = Tenant(name=f"S7 B {stamp}")
        db.add_all([t1, t2])
        db.flush()

        u1 = User(tenant_id=t1.id, email=f"s7-a-{stamp}@example.com",
                  password_hash=hash_password("Test1234!"), role="employee")
        u2 = User(tenant_id=t2.id, email=f"s7-b-{stamp}@example.com",
                  password_hash=hash_password("Test1234!"), role="employee")
        db.add_all([u1, u2])
        db.commit()
        yield {"a": (t1.id, u1.id), "b": (t2.id, u2.id)}
    finally:
        db.rollback()
        # Cascade deletes the tenant's rows
        db.query(Tenant).filter(
            Tenant.id.in_([t.id for t in db.query(Tenant).filter(
                Tenant.name.like(f"S7 % {stamp}")).all()])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_shift_creation(two_tenants):
    t_id, _ = two_tenants["a"]
    db = SessionLocal()
    try:
        shift = Shift(
            tenant_id=t_id,
            name="Day",
            start_time="09:00",
            end_time="18:00",
            grace_minutes=10,
            break_minutes=60,
            overtime_threshold_minutes=30,
        )
        db.add(shift)
        db.commit()
        assert shift.id is not None
        assert shift.is_active is True
    finally:
        db.close()


def test_shift_name_unique_per_tenant(two_tenants):
    from sqlalchemy.exc import IntegrityError
    t_id, _ = two_tenants["a"]
    db = SessionLocal()
    try:
        db.add(Shift(tenant_id=t_id, name="Day",
                     start_time="09:00", end_time="18:00"))
        db.commit()

        db.add(Shift(tenant_id=t_id, name="Day",
                     start_time="10:00", end_time="19:00"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_shift_helpers_isolate_tenants(two_tenants):
    a_t, a_u = two_tenants["a"]
    b_t, b_u = two_tenants["b"]

    db = SessionLocal()
    try:
        db.add_all([
            Shift(tenant_id=a_t, name="A-Shift",
                  start_time="09:00", end_time="18:00"),
            Shift(tenant_id=b_t, name="B-Shift",
                  start_time="09:00", end_time="18:00"),
        ])
        db.commit()

        a_user = db.get(User, a_u)
        b_user = db.get(User, b_u)

        a_shifts = shifts_for_tenant(db, a_user).all()
        b_shifts = shifts_for_tenant(db, b_user).all()

        assert len(a_shifts) == 1
        assert a_shifts[0].name == "A-Shift"
        assert len(b_shifts) == 1
        assert b_shifts[0].name == "B-Shift"
    finally:
        db.close()


def test_shift_assignment_self_scope(two_tenants):
    a_t, a_u = two_tenants["a"]

    db = SessionLocal()
    try:
        shift = Shift(tenant_id=a_t, name="A-Shift",
                      start_time="09:00", end_time="18:00")
        db.add(shift)
        db.flush()

        # Two users in the same tenant: a_u and a second user
        other = User(tenant_id=a_t, email=f"other-{a_u}@example.com",
                     password_hash=hash_password("Test1234!"), role="employee")
        db.add(other)
        db.flush()

        today = date.today()
        end = today + timedelta(days=30)
        db.add_all([
            ShiftAssignment(tenant_id=a_t, user_id=a_u, shift_id=shift.id,
                            start_date=today, end_date=end),
            ShiftAssignment(tenant_id=a_t, user_id=other.id, shift_id=shift.id,
                            start_date=today, end_date=end),
        ])
        db.commit()

        a_user = db.get(User, a_u)
        assignments = shift_assignments_for_self(db, a_user).all()
        assert len(assignments) == 1
        assert assignments[0].user_id == a_u
    finally:
        db.close()


def test_leave_type_and_request(two_tenants):
    a_t, a_u = two_tenants["a"]

    db = SessionLocal()
    try:
        lt = LeaveType(tenant_id=a_t, name="Casual",
                       is_paid=True, annual_entitlement_days=12)
        db.add(lt)
        db.flush()

        lr = LeaveRequest(
            tenant_id=a_t, user_id=a_u, leave_type_id=lt.id,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            days=3.0,
            reason="Family",
            status="pending",
        )
        db.add(lr)
        db.commit()
        assert lr.id is not None
        assert lr.status == "pending"
    finally:
        db.close()


def test_leave_helpers_isolate_tenants(two_tenants):
    a_t, a_u = two_tenants["a"]
    b_t, b_u = two_tenants["b"]

    db = SessionLocal()
    try:
        a_lt = LeaveType(tenant_id=a_t, name="A-Casual")
        b_lt = LeaveType(tenant_id=b_t, name="B-Casual")
        db.add_all([a_lt, b_lt])
        db.flush()

        db.add_all([
            LeaveRequest(tenant_id=a_t, user_id=a_u, leave_type_id=a_lt.id,
                         start_date=date.today(),
                         end_date=date.today(), days=1.0),
            LeaveRequest(tenant_id=b_t, user_id=b_u, leave_type_id=b_lt.id,
                         start_date=date.today(),
                         end_date=date.today(), days=1.0),
        ])
        db.commit()

        a_user = db.get(User, a_u)
        b_user = db.get(User, b_u)

        a_types = leave_types_for_tenant(db, a_user).all()
        b_types = leave_types_for_tenant(db, b_user).all()

        assert len(a_types) == 1
        assert a_types[0].name == "A-Casual"
        assert len(b_types) == 1
        assert b_types[0].name == "B-Casual"

        a_requests = leave_requests_for_self(db, a_user).all()
        b_requests = leave_requests_for_self(db, b_user).all()

        assert len(a_requests) == 1
        assert len(b_requests) == 1
        assert a_requests[0].user_id == a_u
        assert b_requests[0].user_id == b_u
    finally:
        db.close()


def test_lop_unique_constraint(two_tenants):
    from sqlalchemy.exc import IntegrityError
    a_t, a_u = two_tenants["a"]

    db = SessionLocal()
    try:
        today = date.today()
        db.add(LOPRecord(tenant_id=a_t, user_id=a_u, for_date=today,
                         days=1.0, source="unapproved_absence"))
        db.commit()

        db.add(LOPRecord(tenant_id=a_t, user_id=a_u, for_date=today,
                         days=1.0, source="unapproved_absence"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_lop_self_scope(two_tenants):
    a_t, a_u = two_tenants["a"]
    b_t, b_u = two_tenants["b"]

    db = SessionLocal()
    try:
        today = date.today()
        db.add_all([
            LOPRecord(tenant_id=a_t, user_id=a_u, for_date=today,
                      days=1.0, source="manual"),
            LOPRecord(tenant_id=b_t, user_id=b_u, for_date=today,
                      days=1.0, source="manual"),
        ])
        db.commit()

        a_user = db.get(User, a_u)
        records = lop_records_for_self(db, a_user).all()
        assert len(records) == 1
        assert records[0].user_id == a_u
    finally:
        db.close()
