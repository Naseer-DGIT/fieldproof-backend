"""Compare attendance events against a shift assignment.

Given a user and a date, resolve the assigned shift, find the events
for that date, and classify the day:

    on_time      — first check-in at or before start + grace
    late         — first check-in after start + grace
    early_leave  — last check-out before end - break
    absent       — no check-in and no approved leave

An approved leave on the same date takes precedence and is reported as
`on_leave` rather than a status from this module.

This module does not write to the database. It reads events and returns
a classification. The monthly job that populates LOP records calls this.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import AttendanceEvent, LeaveRequest, Shift, ShiftAssignment, User


def _parse_hhmm(value: str) -> time:
    """Parse "HH:MM" to a time object."""
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _combine(day: date, t: time) -> datetime:
    """Combine a date and time into a UTC datetime.

    The stored shift times are local wall-clock. For MVP, the server
    treats them as UTC. A tenant timezone column is a V1.5 concern.
    """
    return datetime.combine(day, t, tzinfo=timezone.utc)


def resolve_shift_for_date(
    db: Session,
    user: User,
    for_date: date,
) -> Shift | None:
    """Return the shift assignment active on `for_date`, or None."""
    assignment = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.tenant_id == user.tenant_id,
            ShiftAssignment.user_id == user.id,
            ShiftAssignment.start_date <= for_date,
            ShiftAssignment.end_date >= for_date,
        )
        .first()
    )
    if assignment is None:
        return None
    return db.get(Shift, assignment.shift_id)


def has_approved_leave(
    db: Session,
    user: User,
    for_date: date,
) -> bool:
    """True if the user has an approved leave request covering `for_date`."""
    row = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.tenant_id == user.tenant_id,
            LeaveRequest.user_id == user.id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= for_date,
            LeaveRequest.end_date >= for_date,
        )
        .first()
    )
    return row is not None


def classify_day(
    db: Session,
    user: User,
    for_date: date,
) -> dict:
    """Classify one day for one user.

    Returns a dict shaped for `ShiftPolicyResult`. Never raises for
    missing data; returns `no_shift` or `absent` instead.
    """
    base = {
        "user_id": user.id,
        "for_date": for_date,
        "shift_name": None,
        "status": "no_shift",
        "first_check_in": None,
        "last_check_out": None,
        "minutes_late": 0,
        "minutes_early_leave": 0,
        "worked_minutes": 0,
    }

    shift = resolve_shift_for_date(db, user, for_date)
    if shift is None:
        return base

    base["shift_name"] = shift.name

    # Approved leave on the same date short-circuits the check.
    if has_approved_leave(db, user, for_date):
        base["status"] = "on_leave"
        return base

    # Find events for that date. The `server_received_at` timestamp is
    # the authoritative time. Client timestamps are not trusted.
    day_start = _combine(for_date, time(0, 0))
    day_end = day_start + timedelta(days=1)

    events = (
        db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.user_id == user.id,
            AttendanceEvent.server_received_at >= day_start,
            AttendanceEvent.server_received_at < day_end,
        )
        .order_by(AttendanceEvent.server_received_at.asc())
        .all()
    )

    check_ins = [e for e in events if e.event_type == "check_in"]
    check_outs = [e for e in events if e.event_type == "check_out"]

    if not check_ins:
        base["status"] = "absent"
        return base

    first_in = check_ins[0].server_received_at
    last_out = check_outs[-1].server_received_at if check_outs else first_in

    base["first_check_in"] = first_in.isoformat()
    base["last_check_out"] = last_out.isoformat() if check_outs else None

    shift_start = _combine(for_date, _parse_hhmm(shift.start_time))
    shift_end = _combine(for_date, _parse_hhmm(shift.end_time))

    grace = timedelta(minutes=shift.grace_minutes)
    late_by = first_in - (shift_start + grace)
    minutes_late = max(0, int(late_by.total_seconds() // 60))
    base["minutes_late"] = minutes_late

    early_by = (shift_end - timedelta(minutes=shift.break_minutes)) - last_out
    minutes_early = max(0, int(early_by.total_seconds() // 60))
    base["minutes_early_leave"] = minutes_early

    worked = last_out - first_in - timedelta(minutes=shift.break_minutes)
    base["worked_minutes"] = max(0, int(worked.total_seconds() // 60))

    if minutes_late > 0:
        base["status"] = "late"
    elif minutes_early > 0 and check_outs:
        base["status"] = "early_leave"
    else:
        base["status"] = "on_time"

    return base
