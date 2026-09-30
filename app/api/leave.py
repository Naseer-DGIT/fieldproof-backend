"""Leave management endpoints.

- Leave types are tenant-scoped and managed by hr_ops / sys_admin.
- Leave requests are created by any authenticated user for themselves.
- Approvals are performed by supervisor / hr_ops / sys_admin.
- Employees see only their own requests. Managers see all in the tenant.
"""

from datetime import date, datetime, timezone

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
from app.core.tenant import leave_requests_for_tenant, leave_types_for_tenant
from app.models import LeaveRequest, LeaveType, User
from app.schemas import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestResponse,
    LeaveTypeCreate,
    LeaveTypeResponse,
)
from app.services.leave import can_cancel, can_decide, validate_new_request

router = APIRouter(prefix="/leave", tags=["leave"])


# --------------------------------------------------------------------------- #
# Leave types
# --------------------------------------------------------------------------- #

@router.post(
    "/types",
    response_model=LeaveTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(EVENTS_LIMIT)
def create_leave_type(
    request: Request,
    body: LeaveTypeCreate,
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
) -> LeaveType:
    existing = (
        leave_types_for_tenant(db, user)
        .filter(LeaveType.name == body.name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A leave type with that name already exists",
        )
    lt = LeaveType(
        tenant_id=user.tenant_id,
        name=body.name,
        is_paid=body.is_paid,
        annual_entitlement_days=body.annual_entitlement_days,
    )
    db.add(lt)
    db.commit()
    db.refresh(lt)
    return lt


@router.get("/types", response_model=list[LeaveTypeResponse])
def list_leave_types(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LeaveType]:
    return leave_types_for_tenant(db, user).order_by(LeaveType.name.asc()).all()


# --------------------------------------------------------------------------- #
# Leave requests
# --------------------------------------------------------------------------- #

@router.post(
    "/requests",
    response_model=LeaveRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(EVENTS_LIMIT)
def create_leave_request(
    request: Request,
    body: LeaveRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequest:
    # The leave type must belong to the caller's tenant.
    lt = (
        leave_types_for_tenant(db, user)
        .filter(LeaveType.id == body.leave_type_id)
        .first()
    )
    if lt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave type not found",
        )

    try:
        validate_new_request(db, user, body.start_date, body.end_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    lr = LeaveRequest(
        tenant_id=user.tenant_id,
        user_id=user.id,
        leave_type_id=lt.id,
        start_date=body.start_date,
        end_date=body.end_date,
        days=body.days,
        reason=body.reason,
        status="pending",
    )
    db.add(lr)
    db.commit()
    db.refresh(lr)
    return lr


@router.get("/requests", response_model=list[LeaveRequestResponse])
def list_leave_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LeaveRequest]:
    """Employees see their own. Managers see the whole tenant.

    An optional status filter is added later if the UI needs it. Today:
    employees get a self-only list; supervisor and above get the tenant.
    """
    q = leave_requests_for_tenant(db, user)
    if user.role == "employee":
        q = q.filter(LeaveRequest.user_id == user.id)
    return q.order_by(LeaveRequest.start_date.desc()).all()


@router.post(
    "/requests/{request_id}/decision",
    response_model=LeaveRequestResponse,
)
@limiter.limit(EVENTS_LIMIT)
def decide_leave_request(
    request: Request,
    request_id: int,
    body: LeaveRequestDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequest:
    if not can_decide(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )

    # Resolve the request inside the caller's tenant.
    lr = (
        leave_requests_for_tenant(db, user)
        .filter(LeaveRequest.id == request_id)
        .first()
    )
    if lr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found",
        )

    if lr.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already {lr.status}",
        )

    lr.status = body.decision
    lr.decided_by = user.id
    lr.decided_at = datetime.now(timezone.utc)
    lr.decision_note = body.note
    db.commit()
    db.refresh(lr)
    return lr


@router.post(
    "/requests/{request_id}/cancel",
    response_model=LeaveRequestResponse,
)
@limiter.limit(EVENTS_LIMIT)
def cancel_leave_request(
    request: Request,
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequest:
    lr = (
        leave_requests_for_tenant(db, user)
        .filter(LeaveRequest.id == request_id)
        .first()
    )
    if lr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found",
        )

    if not can_cancel(user, lr):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot cancel this request",
        )

    lr.status = "cancelled"
    db.commit()
    db.refresh(lr)
    return lr
