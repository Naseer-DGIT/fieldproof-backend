"""Shift management endpoints.

Shifts are tenant-scoped. Only hr_ops and sys_admin may create them.
Supervisors may read and assign.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.limiter import EVENTS_LIMIT, limiter
from app.core.rbac import (
    ROLE_HR_OPS,
    ROLE_SUPERVISOR,
    ROLE_SYS_ADMIN,
    require_role,
)
from app.core.tenant import shifts_for_tenant, shift_assignments_for_tenant
from app.models import Shift, ShiftAssignment, User
from app.schemas import (
    ShiftAssignmentCreate,
    ShiftAssignmentResponse,
    ShiftCreate,
    ShiftResponse,
)

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.post(
    "",
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(EVENTS_LIMIT)
def create_shift(
    request: Request,
    body: ShiftCreate,
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
) -> Shift:
    existing = (
        shifts_for_tenant(db, user)
        .filter(Shift.name == body.name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A shift with that name already exists",
        )

    shift = Shift(
        tenant_id=user.tenant_id,
        name=body.name,
        start_time=body.start_time,
        end_time=body.end_time,
        grace_minutes=body.grace_minutes,
        break_minutes=body.break_minutes,
        overtime_threshold_minutes=body.overtime_threshold_minutes,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.get("", response_model=list[ShiftResponse])
def list_shifts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Shift]:
    return shifts_for_tenant(db, user).order_by(Shift.name.asc()).all()


@router.post(
    "/assignments",
    response_model=ShiftAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(EVENTS_LIMIT)
def assign_shift(
    request: Request,
    body: ShiftAssignmentCreate,
    user: User = Depends(require_role(ROLE_SUPERVISOR, ROLE_HR_OPS, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
) -> ShiftAssignment:
    if body.end_date < body.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be on or after start_date",
        )

    shift = (
        shifts_for_tenant(db, user)
        .filter(Shift.id == body.shift_id)
        .first()
    )
    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found",
        )

    target = (
        db.query(User)
        .filter(
            User.id == body.user_id,
            User.tenant_id == user.tenant_id,
        )
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Overlap check: any existing assignment for this user whose date
    # range intersects the new one.
    overlapping = (
        shift_assignments_for_tenant(db, user)
        .filter(
            ShiftAssignment.user_id == body.user_id,
            ShiftAssignment.start_date <= body.end_date,
            ShiftAssignment.end_date >= body.start_date,
        )
        .first()
    )
    if overlapping is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has a shift assignment in that range",
        )

    assignment = ShiftAssignment(
        tenant_id=user.tenant_id,
        user_id=body.user_id,
        shift_id=body.shift_id,
        start_date=body.start_date,
        end_date=body.end_date,
        assigned_by=user.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/assignments", response_model=list[ShiftAssignmentResponse])
def list_assignments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ShiftAssignment]:
    """List shift assignments.

    Employees see only their own. Supervisors, hr_ops, and sys_admin see
    all assignments in their tenant.
    """
    q = shift_assignments_for_tenant(db, user)
    if user.role == "employee":
        q = q.filter(ShiftAssignment.user_id == user.id)
    return q.order_by(ShiftAssignment.start_date.desc()).all()
