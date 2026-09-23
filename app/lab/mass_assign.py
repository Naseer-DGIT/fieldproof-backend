"""Lab: Mass Assignment — FIXED version.

The vulnerable version copied every supplied field onto the User model.
The fix uses an explicit allowlist and rejects requests that contain
any field outside it.

Rejecting the whole request (400/422) matters more than silently
ignoring disallowed fields: the client learns its request was refused
instead of assuming the write succeeded.

CWE-915, OWASP API3:2023 Broken Object Property Level Authorization.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models import User

router = APIRouter(prefix="/lab/profile", tags=["lab"])

# Only these fields may be changed by the caller.
WRITABLE_FIELDS = {"email", "team_id"}


class UpdateRequest(BaseModel):
    """Explicit allowlist. `extra="forbid"` rejects any other field."""
    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    team_id: int | None = None


@router.patch("/update")
def update_profile(
    body: UpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Update the caller's profile. Only allowlisted fields are writable."""
    updates = body.model_dump(exclude_unset=True)

    unexpected = set(updates.keys()) - WRITABLE_FIELDS
    if unexpected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"fields not writable: {sorted(unexpected)}",
        )

    for field, value in updates.items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "team_id": user.team_id,
        "is_active": user.is_active,
    }
