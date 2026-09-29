"""LOP endpoints.

Computing LOP is a manual operation today. S14 wires a scheduled job.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.limiter import EVENTS_LIMIT, limiter
from app.core.rbac import ROLE_HR_OPS, ROLE_SYS_ADMIN, require_role
from app.core.tenant import lop_records_for_tenant
from app.models import LOPRecord, User
from app.schemas import ShiftPolicyResult  # not used here, imported for symmetry
from app.services.lop import compute_for_range

router = APIRouter(prefix="/lop", tags=["lop"])


class LOPResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    for_date: date
    days: float
    source: str
    note: str | None

    class Config:
        from_attributes = True


class ComputeRequest(BaseModel):
    start: date
    end: date


class ComputeResult(BaseModel):
    inserted: int
    updated: int
    skipped_leave: int
    skipped_no_shift: int


@router.post(
    "/compute",
    response_model=ComputeResult,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(EVENTS_LIMIT)
def compute(
    request: Request,
    body: ComputeRequest = Body(...),
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
) -> ComputeResult:
    """Recompute LOP for the caller's tenant over the given range.

    Idempotent: rerunning over the same range updates existing rows.
    """
    if body.end < body.start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end must be on or after start",
        )
    if (body.end - body.start) > timedelta(days=62):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Range may not exceed 62 days",
        )

    counts = compute_for_range(db, user.tenant_id, body.start, body.end)
    return ComputeResult(**counts)


@router.get("", response_model=list[LOPResponse])
def list_lop(
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
) -> list[LOPRecord]:
    """List all LOP records in the caller's tenant.

    Requires hr_ops or sys_admin. Employees will have a self-only
    variant on Day 7.
    """
    return (
        lop_records_for_tenant(db, user)
        .order_by(LOPRecord.for_date.desc())
        .limit(500)
        .all()
    )
