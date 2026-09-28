"""Leave request business logic.

Rules:
  - An employee may request leave only for dates not in the past.
  - A request may not overlap another pending or approved request.
  - Only the requester may cancel their own pending request.
  - Only supervisor, hr_ops, or sys_admin may approve or reject.
  - Cancelled and decided requests are terminal; no further transitions.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import LeaveRequest, User


def _overlaps(
    db: Session,
    user_id: int,
    start: date,
    end: date,
) -> LeaveRequest | None:
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
        .first()
    )


def validate_new_request(
    db: Session,
    user: User,
    start: date,
    end: date,
) -> None:
    """Raise ValueError with a specific message on any invalid request."""
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    if start < date.today():
        raise ValueError("start_date may not be in the past")
    existing = _overlaps(db, user.id, start, end)
    if existing is not None:
        raise ValueError(
            "Overlaps an existing request "
            f"(id={existing.id}, status={existing.status})"
        )


def can_decide(actor: User) -> bool:
    return actor.role in ("supervisor", "hr_ops", "sys_admin")


def can_cancel(actor: User, request: LeaveRequest) -> bool:
    """A user may cancel their own pending request. HR may cancel any."""
    if actor.role in ("hr_ops", "sys_admin"):
        return request.status in ("pending", "approved")
    return actor.id == request.user_id and request.status == "pending"
