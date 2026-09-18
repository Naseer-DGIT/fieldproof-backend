"""Role-based access control for FieldProof.

Every privileged endpoint depends on `require_role(...)` instead of
`get_current_user` alone. Roles come from the JWT, which was signed by
the auth service at login. The JWT is valid for 1h — a role change
takes up to 1h to propagate. If that window is unacceptable, add a
database role check in front of `require_role`.
"""

from fastapi import Depends, HTTPException, status

from app.core.auth import get_current_user
from app.models import User

# Roles are defined in one place so a typo in an endpoint is caught at
# import time, not at runtime.
ROLE_EMPLOYEE = "employee"
ROLE_SUPERVISOR = "supervisor"
ROLE_HR_OPS = "hr_ops"
ROLE_SECURITY_ADMIN = "security_admin"
ROLE_SYS_ADMIN = "sys_admin"

ALL_ROLES = {
    ROLE_EMPLOYEE,
    ROLE_SUPERVISOR,
    ROLE_HR_OPS,
    ROLE_SECURITY_ADMIN,
    ROLE_SYS_ADMIN,
}

# Hierarchy for "at least this role" checks. Higher number = more scope.
ROLE_RANK = {
    ROLE_EMPLOYEE: 10,
    ROLE_SUPERVISOR: 20,
    ROLE_HR_OPS: 30,
    ROLE_SECURITY_ADMIN: 40,
    ROLE_SYS_ADMIN: 50,
}


def require_role(*allowed: str):
    """FastAPI dependency factory.

    Usage:
        @router.post("/approve", dependencies=[Depends(require_role(ROLE_SUPERVISOR))])

    Or, when the handler needs the user:

        def approve(user: User = Depends(require_role(ROLE_SUPERVISOR))): ...

    Any role in `allowed` passes. Everyone else gets 403.
    """
    allowed_set = set(allowed)
    unknown = allowed_set - ALL_ROLES
    if unknown:
        raise ValueError(f"Unknown roles in require_role: {unknown}")

    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user

    return dep


def require_min_role(minimum: str):
    """FastAPI dependency factory. Requires a role at or above `minimum`.

    Uses ROLE_RANK. Example:
        require_min_role(ROLE_HR_OPS)   # hr_ops, security_admin, sys_admin
    """
    if minimum not in ROLE_RANK:
        raise ValueError(f"Unknown role: {minimum}")
    floor = ROLE_RANK[minimum]

    def dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < floor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user

    return dep


def require_same_tenant(user: User, tenant_id: int) -> None:
    """Raise 403 if the user is not in `tenant_id`.

    Called inline from a handler when the resource's tenant is known
    from the database. Do not trust a tenant_id from the request body.
    """
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied",
        )
