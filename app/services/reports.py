"""Report generation.

Each report is a generator that yields dict rows. The router converts
to JSON or CSV depending on the `format` query parameter.

The generators are lazy: they compute one row at a time so the caller
never holds the full result set in memory. For the per-user reports
that query analytics per user, the cost is one query batch per user.
Acceptable for tenants with hundreds of users. Tenants with thousands
will need a batching refactor (S14).
"""

from datetime import date
from typing import Iterator

from sqlalchemy.orm import Session

from app.models import LOPRecord, User
from app.services.analytics import summary_for_range


def attendance_summary_rows(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> Iterator[dict]:
    """One row per (user, day) across the tenant.

    Columns: user_id, for_date, shift_name, status, worked_minutes,
    scheduled_minutes, minutes_late, overtime_minutes.
    """
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.id.asc())
        .all()
    )

    for user in users:
        for day in summary_for_range(db, user, start, end):
            yield {
                "user_id": user.id,
                "for_date": day["for_date"].isoformat(),
                "shift_name": day["shift_name"],
                "status": day["status"],
                "worked_minutes": day["worked_minutes"],
                "scheduled_minutes": day["scheduled_minutes"],
                "minutes_late": day["minutes_late"],
                "overtime_minutes": day["overtime_minutes"],
            }


def work_hours_rows(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> Iterator[dict]:
    """One row per user, aggregated over the range.

    Columns: user_id, days_with_shift, worked_minutes,
    scheduled_minutes, overtime_minutes, avg_worked_minutes.
    """
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.id.asc())
        .all()
    )

    for user in users:
        days = summary_for_range(db, user, start, end)
        if not days:
            continue

        worked = sum(d["worked_minutes"] for d in days)
        scheduled = sum(d["scheduled_minutes"] for d in days)
        overtime = sum(d["overtime_minutes"] for d in days)
        count = len(days)

        yield {
            "user_id": user.id,
            "days_with_shift": count,
            "worked_minutes": worked,
            "scheduled_minutes": scheduled,
            "overtime_minutes": overtime,
            "avg_worked_minutes": round(worked / count, 1) if count else 0.0,
        }


def break_report_rows(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> Iterator[dict]:
    """One row per user, break totals over the range.

    Columns: user_id, break_count, total_break_minutes,
    longest_break_minutes, avg_break_minutes.
    """
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.id.asc())
        .all()
    )

    for user in users:
        days = summary_for_range(db, user, start, end)
        if not days:
            continue

        count = sum(d["break_count"] for d in days)
        total = sum(d["total_break_minutes"] for d in days)
        longest = max((d["longest_break_minutes"] for d in days), default=0)

        yield {
            "user_id": user.id,
            "break_count": count,
            "total_break_minutes": total,
            "longest_break_minutes": longest,
            "avg_break_minutes": round(total / count, 1) if count else 0.0,
        }


def lop_report_rows(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
) -> Iterator[dict]:
    """One row per LOP record in the range.

    Columns: user_id, for_date, days, source, note.
    """
    rows = (
        db.query(LOPRecord)
        .filter(
            LOPRecord.tenant_id == tenant_id,
            LOPRecord.for_date >= start,
            LOPRecord.for_date <= end,
        )
        .order_by(LOPRecord.for_date.asc(), LOPRecord.user_id.asc())
        .all()
    )

    for r in rows:
        yield {
            "user_id": r.user_id,
            "for_date": r.for_date.isoformat(),
            "days": float(r.days),
            "source": r.source,
            "note": r.note or "",
        }
