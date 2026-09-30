"""Report endpoints.

Every report accepts `format=json` (default) or `format=csv`. CSV is
streamed. Reports are tenant-scoped and require hr_ops or above.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.csv_stream import streaming_csv
from app.core.db import get_db
from app.core.rbac import (
    ROLE_HR_OPS,
    ROLE_SECURITY_ADMIN,
    ROLE_SYS_ADMIN,
    require_role,
)
from app.models import User
from app.services.reports import (
    attendance_summary_rows,
    break_report_rows,
    lop_report_rows,
    work_hours_rows,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_MAX_DAYS = 62


def _validate(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end must be on or after start",
        )
    if (end - start) > timedelta(days=_MAX_DAYS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Range may not exceed {_MAX_DAYS} days",
        )


def _require_hr(user: User) -> User:
    if user.role not in ("hr_ops", "security_admin", "sys_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
    return user


def _respond(
    rows,
    fmt: str,
    filename: str,
):
    if fmt == "csv":
        return streaming_csv(rows, filename)
    # JSON: materialize. The report cap is 62 days, so the row count is
    # bounded by users × days, which for a hundred users is 6200 rows.
    return JSONResponse(content=list(rows))


@router.get("/attendance-summary")
def attendance_summary(
    start: date = Query(...),
    end: date = Query(...),
    format: str = Query("json", pattern=r"^(json|csv)$"),
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SECURITY_ADMIN, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
):
    """Per-day attendance for every user in the tenant."""
    _validate(start, end)
    rows = attendance_summary_rows(db, user.tenant_id, start, end)
    return _respond(rows, format, f"attendance-{start}-{end}.csv")


@router.get("/work-hours")
def work_hours(
    start: date = Query(...),
    end: date = Query(...),
    format: str = Query("json", pattern=r"^(json|csv)$"),
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SECURITY_ADMIN, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
):
    """Aggregated work hours per user."""
    _validate(start, end)
    rows = work_hours_rows(db, user.tenant_id, start, end)
    return _respond(rows, format, f"work-hours-{start}-{end}.csv")


@router.get("/breaks")
def breaks(
    start: date = Query(...),
    end: date = Query(...),
    format: str = Query("json", pattern=r"^(json|csv)$"),
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SECURITY_ADMIN, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
):
    """Break analysis per user."""
    _validate(start, end)
    rows = break_report_rows(db, user.tenant_id, start, end)
    return _respond(rows, format, f"breaks-{start}-{end}.csv")


@router.get("/lop")
def lop(
    start: date = Query(...),
    end: date = Query(...),
    format: str = Query("json", pattern=r"^(json|csv)$"),
    user: User = Depends(require_role(ROLE_HR_OPS, ROLE_SECURITY_ADMIN, ROLE_SYS_ADMIN)),
    db: Session = Depends(get_db),
):
    """LOP records in the range."""
    _validate(start, end)
    rows = lop_report_rows(db, user.tenant_id, start, end)
    return _respond(rows, format, f"lop-{start}-{end}.csv")
