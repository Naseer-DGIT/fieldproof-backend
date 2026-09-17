from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models import Device, User
from app.schemas import DeviceRegisterRequest, DeviceResponse

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post(
    "/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_device(
    body: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Device:
    """Register a device public key for the authenticated user.

    Idempotent: if the same public key is already registered for this user,
    the existing row is returned instead of creating a duplicate.

    A device may be re-registered (e.g. reinstall) but the previous key
    must not be silently replaced for a different user.
    """
    existing = (
        db.query(Device)
        .filter(
            Device.user_id == user.id,
            Device.public_key == body.public_key,
            Device.revoked.is_(False),
        )
        .first()
    )
    if existing is not None:
        return existing

    # A user may have at most one active device in MVP. Re-registering
    # replaces the previous binding (revoked, not deleted) so the audit
    # trail is preserved.
    previous = (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .all()
    )
    for dev in previous:
        dev.revoked = True

    device = Device(
        user_id=user.id,
        public_key=body.public_key,
        platform=body.platform,
        attestation_status="PENDING",
        revoked=False,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/me", response_model=DeviceResponse)
def current_device(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Device:
    device = (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .first()
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active device registered",
        )
    return device
