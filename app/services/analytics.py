"""Workforce analytics aggregations.

For a user and a date range, produce one row per day with:

  scheduled_minutes    — the shift length minus break
  worked_minutes       — last check-out minus first check-in, minus breaks
  break_count          — number of break_start/break_end pairs
  total_break_minutes  — sum of break durations
  longest_break_minutes — the single longest break
  minutes_late         — check-in minus (shift start + grace)
  overtime_minutes     — last check-out minus (shift end + threshold)
  status               — on_time | late | early_leave | absent | on_leave | no_shift

Only days with a shift assignment are included. Days with no shift and
no events are skipped — they are not part of the analysis.

The service reads events. It does not write. The LOP computation on
Day 4 uses a subset of this logic; keeping them separate avoids
coupling the write path to the read path.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import AttendanceEvent, LeaveRequest, Shift, ShiftAssignment, User


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _combine(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=timezone.utc)


def _daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current = current + timedelta(days=1)


def _shift_for(db: Session, user: User, day: date) -> Shift | None:
    assignment = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.tenant_id == user.tenant_id,
            ShiftAssignment.user_id == user.id,
            ShiftAssignment.start_date <= day,
            ShiftAssignment.end_date >= day,
        )
        .first()
    )
    if assignment is None:
        return None
    return db.get(Shift, assignment.shift_id)


def _approved_leave(db: Session, user: User, day: date) -> bool:
    row = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.tenant_id == user.tenant_id,
            LeaveRequest.user_id == user.id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= day,
            LeaveRequest.end_date >= day,
        )
        .first()
    )
    return row is not None


def _events_for_day(db: Session, user: User, day: date) -> list[AttendanceEvent]:
    start = _combine(day, time(0, 0))
    end = start + timedelta(days=1)
    return (
        db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.user_id == user.id,
            AttendanceEvent.server_received_at >= start,
            AttendanceEvent.server_received_at < end,
        )
        .order_by(AttendanceEvent.server_received_at.asc())
        .all()
    )


def _breaks_minutes(events: list[AttendanceEvent]) -> tuple[int, int, int]:
    """Return (count, total_minutes, longest_minutes) for completed breaks.

    A break is paired: break_start followed by break_end, in time order.
    Unclosed breaks are ignored — the ended_at is unknown.
    """
    starts: list[datetime] = []
    total = 0
    longest = 0
    count = 0

    for e in events:
        if e.event_type == "break_start":
            starts.append(e.server_received_at)
        elif e.event_type == "break_end" and starts:
            start = starts.pop(0)
            minutes = int((e.server_received_at - start).total_seconds() // 60)
            minutes = max(0, minutes)
            total += minutes
            longest = max(longest, minutes)
            count += 1

    return count, total, longest


def day_summary(db: Session, user: User, day: date) -> dict | None:
    """Aggregate one day. Returns None if the user has no shift on that day."""
    shift = _shift_for(db, user, day)
    if shift is None:
        return None

    scheduled_start = _combine(day, _parse_hhmm(shift.start_time))
    scheduled_end = _combine(day, _parse_hhmm(shift.end_time))
    scheduled_minutes = int(
        (scheduled_end - scheduled_start).total_seconds() // 60
    ) - shift.break_minutes

    base = {
        "for_date": day,
        "shift_name": shift.name,
        "scheduled_minutes": max(0, scheduled_minutes),
        "worked_minutes": 0,
        "break_count": 0,
        "total_break_minutes": 0,
        "longest_break_minutes": 0,
        "minutes_late": 0,
        "overtime_minutes": 0,
        "status": "absent",
    }

    if _approved_leave(db, user, day):
        base["status"] = "on_leave"
        return base

    events = _events_for_day(db, user, day)
    check_ins = [e for e in events if e.event_type == "check_in"]
    check_outs = [e for e in events if e.event_type == "check_out"]

    break_count, total_break, longest_break = _breaks_minutes(events)
    base["break_count"] = break_count
    base["total_break_minutes"] = total_break
    base["longest_break_minutes"] = longest_break

    if not check_ins:
        return base

    first_in = check_ins[0].server_received_at
    last_out = check_outs[-1].server_received_at if check_outs else first_in

    # Worked minutes: from first check-in to last check-out, minus
    # recorded breaks. If no check-out, worked is zero (the day is not
    # closed).
    if check_outs:
        gross = int((last_out - first_in).total_seconds() // 60)
        base["worked_minutes"] = max(0, gross - total_break)

    # Late: check-in after start + grace
    grace_delta = timedelta(minutes=shift.grace_minutes)
    late_by = first_in - (scheduled_start + grace_delta)
    base["minutes_late"] = max(0, int(late_by.total_seconds() // 60))

    # Overtime: check-out after end + threshold, but only if there was
    # a check-out.
    if check_outs:
        threshold = timedelta(minutes=shift.overtime_threshold_minutes)
        over_by = last_out - (scheduled_end + threshold)
        base["overtime_minutes"] = max(0, int(over_by.total_seconds() // 60))

    # Status
    early_threshold = scheduled_end - timedelta(minutes=shift.break_minutes)
    if base["minutes_late"] > 0:
        base["status"] = "late"
    elif check_outs and last_out < early_threshold:
        base["status"] = "early_leave"
    else:
        base["status"] = "on_time"

    return base


def summary_for_range(
    db: Session,
    user: User,
    start: date,
    end: date,
) -> list[dict]:
    """One row per day in the range where the user had a shift."""
    out: list[dict] = []
    for day in _daterange(start, end):
        row = day_summary(db, user, day)
        if row is not None:
            out.append(row)
    return out
