"""Loss of Pay computation.

Given a date range, walk every day for every user with a shift
assignment and produce LOP records for days that qualify.

Sources:
  unapproved_absence — no check-in, no approved leave
  late_arrival       — check-in after grace window (half day)
  insufficient_hours — worked minutes < half the shift length (half day)

Manual LOP is set by HR through a separate endpoint (Day 7) and is not
touched by this service.

The service is idempotent: the `(user_id, for_date, source)` unique
constraint means a second run updates existing rows rather than
duplicating them.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import LOPRecord, Shift, ShiftAssignment, User
from app.services.shift_policy import classify_day


def _daterange(start: date, end: date):
    """Yield every date from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current = current + timedelta(days=1)


def _upsert(
    db: Session,
    tenant_id: int,
    user_id: int,
    for_date: date,
    days: float,
    source: str,
    note: str,
) -> bool:
    """Insert or update an LOP row. Returns True if inserted, False if updated."""
    existing = (
        db.query(LOPRecord)
        .filter(
            LOPRecord.user_id == user_id,
            LOPRecord.for_date == for_date,
            LOPRecord.source == source,
        )
        .first()
    )
    if existing is not None:
        existing.days = days
        existing.note = note
        return False

    db.add(LOPRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        for_date=for_date,
        days=days,
        source=source,
        note=note,
    ))
    return True


def compute_for_range(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> dict:
    """Compute LOP for all users in a tenant over a date range.

    Returns counts: {inserted, updated, skipped_leave, skipped_no_shift}.
    """
    if end < start:
        raise ValueError("end must be on or after start")

    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .all()
    )

    counts = {
        "inserted": 0,
        "updated": 0,
        "skipped_leave": 0,
        "skipped_no_shift": 0,
    }

    for user in users:
        for day in _daterange(start, end):
            result = classify_day(db, user, day)

            if result["status"] == "no_shift":
                counts["skipped_no_shift"] += 1
                continue
            if result["status"] == "on_leave":
                counts["skipped_leave"] += 1
                continue

            shift = (
                db.query(Shift)
                .filter(Shift.tenant_id == tenant_id)
                .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
                .filter(
                    ShiftAssignment.user_id == user.id,
                    ShiftAssignment.start_date <= day,
                    ShiftAssignment.end_date >= day,
                )
                .first()
            )
            if shift is None:
                counts["skipped_no_shift"] += 1
                continue

            # Compute the shift length for the insufficient-hours check.
            def _hhmm(value: str) -> time:
                h, m = value.split(":")
                return time(int(h), int(m))

            start_dt = datetime.combine(day, _hhmm(shift.start_time), tzinfo=timezone.utc)
            end_dt = datetime.combine(day, _hhmm(shift.end_time), tzinfo=timezone.utc)
            shift_minutes = int((end_dt - start_dt).total_seconds() // 60)

            status = result["status"]
            inserted = False

            if status == "absent":
                inserted = _upsert(
                    db, tenant_id, user.id, day, 1.0,
                    "unapproved_absence", "No check-in and no approved leave",
                )
            elif status == "late":
                inserted = _upsert(
                    db, tenant_id, user.id, day, 0.5,
                    "late_arrival",
                    f"Checked in {result['minutes_late']} minutes after grace",
                )
            elif status in ("on_time", "early_leave"):
                half = shift_minutes // 2
                if result["worked_minutes"] < half:
                    inserted = _upsert(
                        db, tenant_id, user.id, day, 0.5,
                        "insufficient_hours",
                        f"Worked {result['worked_minutes']} of {shift_minutes} minutes",
                    )
                else:
                    # Day is fine: no LOP to create.
                    continue
            else:
                # Unknown status; do not guess.
                continue

            counts["inserted" if inserted else "updated"] += 1

    db.commit()
    return counts
