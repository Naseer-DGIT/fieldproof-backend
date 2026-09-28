"""Helpers for tenant-scoped queries.

Use these instead of writing a raw query in an endpoint. A helper that
takes a `User` cannot accidentally drop the tenant filter — the filter
is inside the helper.
"""

from sqlalchemy.orm import Query, Session

from app.models import AttendanceEvent, Device, User


def tenant_user_ids(db: Session, user: User) -> Query:
    """Return a query of user ids in the same tenant as `user`.

    Callers use this as a subquery:
        .filter(AttendanceEvent.user_id.in_(tenant_user_ids(db, user)))
    """
    return db.query(User.id).filter(User.tenant_id == user.tenant_id)


def events_for_tenant(db: Session, user: User) -> Query:
    """Attendance events in the caller's tenant.

    Used by admin and supervisor endpoints. Ordinary users should use
    `events_for_self`.
    """
    return (
        db.query(AttendanceEvent)
        .join(User, AttendanceEvent.user_id == User.id)
        .filter(User.tenant_id == user.tenant_id)
    )


def events_for_self(db: Session, user: User) -> Query:
    """Attendance events for the caller only. Cross-tenant is impossible
    because the filter is on the caller's own user id, which came from
    the signed JWT."""
    return db.query(AttendanceEvent).filter(AttendanceEvent.user_id == user.id)


def devices_for_self(db: Session, user: User) -> Query:
    return db.query(Device).filter(Device.user_id == user.id)


def active_device_for_self(db: Session, user: User) -> Device | None:
    return (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .first()
    )


def active_devices_for_self(db: Session, user: User) -> list[Device]:
    return (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .all()
    )


def events_for_team(db: Session, user: User) -> Query:
    """Events for the calling supervisor's team, inside their tenant.

    Preconditions: `user.team_id` must be non-null. The endpoint checks
    this and returns 403 before calling the helper.

    The tenant filter is redundant if team ids are globally unique, but
    this code does not assume that. Two tenants may both have a team
    with id 1; the join keeps them separate.
    """
    return (
        db.query(AttendanceEvent)
        .join(User, AttendanceEvent.user_id == User.id)
        .filter(
            User.tenant_id == user.tenant_id,
            User.team_id == user.team_id,
        )
    )


# --------------------------------------------------------------------------- #
# S7 — shift and leave helpers
# --------------------------------------------------------------------------- #

def shifts_for_tenant(db: Session, user: User) -> Query:
    """All active shifts in the caller's tenant."""
    from app.models import Shift
    return (
        db.query(Shift)
        .filter(
            Shift.tenant_id == user.tenant_id,
            Shift.is_active.is_(True),
        )
    )


def shift_assignments_for_tenant(db: Session, user: User) -> Query:
    """All shift assignments in the caller's tenant."""
    from app.models import ShiftAssignment
    return (
        db.query(ShiftAssignment)
        .filter(ShiftAssignment.tenant_id == user.tenant_id)
    )


def shift_assignments_for_self(db: Session, user: User) -> Query:
    """Shift assignments for the caller only."""
    from app.models import ShiftAssignment
    return (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.tenant_id == user.tenant_id,
            ShiftAssignment.user_id == user.id,
        )
    )


def leave_types_for_tenant(db: Session, user: User) -> Query:
    """Active leave types in the caller's tenant."""
    from app.models import LeaveType
    return (
        db.query(LeaveType)
        .filter(
            LeaveType.tenant_id == user.tenant_id,
            LeaveType.is_active.is_(True),
        )
    )


def leave_requests_for_tenant(db: Session, user: User) -> Query:
    """All leave requests in the caller's tenant."""
    from app.models import LeaveRequest
    return (
        db.query(LeaveRequest)
        .filter(LeaveRequest.tenant_id == user.tenant_id)
    )


def leave_requests_for_self(db: Session, user: User) -> Query:
    """Leave requests for the caller only."""
    from app.models import LeaveRequest
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.tenant_id == user.tenant_id,
            LeaveRequest.user_id == user.id,
        )
    )


def lop_records_for_tenant(db: Session, user: User) -> Query:
    """All LOP records in the caller's tenant."""
    from app.models import LOPRecord
    return (
        db.query(LOPRecord)
        .filter(LOPRecord.tenant_id == user.tenant_id)
    )


def lop_records_for_self(db: Session, user: User) -> Query:
    """LOP records for the caller only."""
    from app.models import LOPRecord
    return (
        db.query(LOPRecord)
        .filter(
            LOPRecord.tenant_id == user.tenant_id,
            LOPRecord.user_id == user.id,
        )
    )
