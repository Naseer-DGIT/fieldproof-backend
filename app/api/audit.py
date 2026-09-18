"""Audit verification endpoints.

These endpoints are read-only and require the highest role. They do
not modify the audit trail and do not return its contents — only
metadata about its integrity.
"""

from fastapi import APIRouter, Depends

from app.core.rbac import ROLE_SYS_ADMIN, require_role
from app.models import User
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/verify")
def verify(
    user: User = Depends(require_role(ROLE_SYS_ADMIN)),
) -> dict:
    """Walk the audit chain and report integrity.

    Returns counts and the first break, if any. Does not return row
    contents. Requires sys_admin.
    """
    result = verify_chain()
    return {
        "rows_checked": result["rows_checked"],
        "breaks": result["breaks"],
        "ok": len(result["breaks"]) == 0,
    }
