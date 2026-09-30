"""Analytics endpoints.

Read-only aggregates over the caller's own events, or another user's
events if the caller is supervisor, hr_ops, or sys_admin.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.rbac import ROLE_SUPERVISOR, require_min_role
from app.models import User
from app.services.analytics import summary_for_range

router = APIRouter(prefix="/analytics", tags=["analytics"])


class DaySummary(BaseModel):
    for_date: date
    shift_name: str
    scheduled_minutes: int
    worked_minutes: int
    break_count: int
    total_break_minutes: int
    longest_break_minutes: int
    minutes_late: int
    overtime_minutes: int
    status: str


class AnalyticsResponse(BaseModel):
    user_id: int
    start: date
    end: date
    days: list[DaySummary]


def _validate_range(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end must be on or after start",
        )
    if (end - start) > timedelta(days=62):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Range may not exceed 62 days",
        )


@router.get("/me", response_model=AnalyticsResponse)
def analytics_me(
    start: date = Query(...),
    end: date = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    """Aggregates for the caller."""
    _validate_range(start, end)
    rows = summary_for_range(db, user, start, end)
    return AnalyticsResponse(
        user_id=user.id,
        start=start,
        end=end,
        days=[DaySummary(**r) for r in rows],
    )


@router.get("/users/{user_id}", response_model=AnalyticsResponse)
def analytics_user(
    user_id: int,
    start: date = Query(...),
    end: date = Query(...),
    actor: User = Depends(require_min_role(ROLE_SUPERVISOR)),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    """Aggregates for another user in the caller's tenant.

    A supervisor may only query users in their team. hr_ops, security_admin,
    and sys_admin may query any user in the tenant.
    """
    _validate_range(start, end)

    target = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.tenant_id == actor.tenant_id,
        )
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if actor.role == "supervisor":
        # Supervisors may only read their own team.
        if target.team_id != actor.team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    rows = summary_for_range(db, target, start, end)
    return AnalyticsResponse(
        user_id=target.id,
        start=start,
        end=end,
        days=[DaySummary(**r) for r in rows],
    )
