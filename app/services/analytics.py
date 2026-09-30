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


# --------------------------------------------------------------------------- #
# S7 Day 6 — tenant-wide aggregations
# --------------------------------------------------------------------------- #

def _active_users(db: Session, tenant_id: int) -> list[User]:
    return (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .all()
    )


def tenant_rollup(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> dict:
    """Aggregate every user's days into one row.

    `attendance_rate` = (days_present + days_on_leave) / days_with_shift.
    A day with no shift assignment is not counted in the denominator.
    """
    users = _active_users(db, tenant_id)

    total = {
        "user_count": len(users),
        "days_with_shift": 0,
        "days_present": 0,
        "days_absent": 0,
        "days_on_leave": 0,
        "days_late": 0,
        "days_early_leave": 0,
        "days_on_time": 0,
        "worked_minutes": 0,
        "scheduled_minutes": 0,
        "overtime_minutes": 0,
        "minutes_late": 0,
        "break_count": 0,
        "total_break_minutes": 0,
    }

    for user in users:
        for row in summary_for_range(db, user, start, end):
            total["days_with_shift"] += 1
            total["worked_minutes"] += row["worked_minutes"]
            total["scheduled_minutes"] += row["scheduled_minutes"]
            total["overtime_minutes"] += row["overtime_minutes"]
            total["minutes_late"] += row["minutes_late"]
            total["break_count"] += row["break_count"]
            total["total_break_minutes"] += row["total_break_minutes"]

            status = row["status"]
            if status == "absent":
                total["days_absent"] += 1
            elif status == "on_leave":
                total["days_on_leave"] += 1
            elif status in ("on_time", "late", "early_leave"):
                total["days_present"] += 1
                if status == "late":
                    total["days_late"] += 1
                elif status == "early_leave":
                    total["days_early_leave"] += 1
                else:
                    total["days_on_time"] += 1

    denom = total["days_with_shift"]
    present_or_leave = total["days_present"] + total["days_on_leave"]
    total["attendance_rate"] = round(present_or_leave / denom, 4) if denom else 0.0

    return total


def by_shift(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Aggregate by shift name across the tenant."""
    users = _active_users(db, tenant_id)
    buckets: dict[str, dict] = {}

    for user in users:
        for row in summary_for_range(db, user, start, end):
            name = row["shift_name"]
            if name not in buckets:
                buckets[name] = {
                    "shift_name": name,
                    "days_with_shift": 0,
                    "days_present": 0,
                    "days_absent": 0,
                    "days_late": 0,
                    "worked_minutes": 0,
                    "scheduled_minutes": 0,
                    "overtime_minutes": 0,
                }
            b = buckets[name]
            b["days_with_shift"] += 1
            b["worked_minutes"] += row["worked_minutes"]
            b["scheduled_minutes"] += row["scheduled_minutes"]
            b["overtime_minutes"] += row["overtime_minutes"]

            status = row["status"]
            if status in ("on_time", "late", "early_leave"):
                b["days_present"] += 1
            if status == "absent":
                b["days_absent"] += 1
            if status == "late":
                b["days_late"] += 1

    return sorted(buckets.values(), key=lambda x: x["shift_name"])


def by_team(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Aggregate by `team_id`.

    Users with no team (`team_id is None`) are grouped under a single
    bucket so the count is complete. The endpoint labels that bucket
    as `unassigned`.
    """
    users = _active_users(db, tenant_id)
    buckets: dict[int | None, dict] = {}

    for user in users:
        team_id = user.team_id
        if team_id not in buckets:
            buckets[team_id] = {
                "team_id": team_id,
                "user_count": 0,
                "days_with_shift": 0,
                "days_present": 0,
                "days_absent": 0,
                "days_late": 0,
                "worked_minutes": 0,
                "overtime_minutes": 0,
            }
        b = buckets[team_id]
        b["user_count"] += 1

        for row in summary_for_range(db, user, start, end):
            b["days_with_shift"] += 1
            b["worked_minutes"] += row["worked_minutes"]
            b["overtime_minutes"] += row["overtime_minutes"]

            status = row["status"]
            if status in ("on_time", "late", "early_leave"):
                b["days_present"] += 1
            if status == "absent":
                b["days_absent"] += 1
            if status == "late":
                b["days_late"] += 1

    # Sort by team_id; None sorts last.
    return sorted(
        buckets.values(),
        key=lambda x: (x["team_id"] is None, x["team_id"] or 0),
    )
