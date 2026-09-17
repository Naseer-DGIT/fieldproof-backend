"""Attendance event ingestion.

Verification order (do not reorder):
  1. Authenticate the principal.
  2. Resolve the active device for the user.
  3. Decode the signed payload bytes.
  4. Verify the Ed25519 signature against the device's public key.
  5. Enforce the previous_hash chain for this device.
  6. Enforce idempotency (event_id and idempotency_key).
  7. Persist.

Any step failing returns a specific status code so the client can
distinguish a retryable error from a rejected event.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models import AttendanceEvent, Device, User
from app.schemas import AttendanceEventIn, AttendanceEventOut
from app.services.signatures import b64url_decode, verify_ed25519

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _active_device(db: Session, user: User) -> Device:
    device = (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .first()
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active device registered for this user",
        )
    return device


@router.post(
    "/events",
    response_model=AttendanceEventOut,
    status_code=status.HTTP_201_CREATED,
)
def post_event(
    body: AttendanceEventIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendanceEventOut:
    device = _active_device(db, user)

    # 1. Decode the signed bytes. These are the exact bytes the device
    #    signed. Parse them separately for indexing.
    try:
        signed_bytes = b64url_decode(body.payload_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload_b64 is not valid base64url",
        )

    # 2. Verify signature.
    if not verify_ed25519(device.public_key, signed_bytes, body.signature_b64):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signature verification failed",
        )

    # 3. Parse the payload to confirm it matches the declared fields.
    try:
        payload = json.loads(signed_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signed payload is not valid UTF-8 JSON",
        )

    if payload.get("event_id") != body.event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload.event_id does not match body.event_id",
        )
    if payload.get("type") != body.event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload.type does not match body.event_type",
        )

    # 4. Idempotency: if this event_id was already accepted, return it.
    existing = (
        db.query(AttendanceEvent)
        .filter(AttendanceEvent.event_id == body.event_id)
        .first()
    )
    if existing is not None:
        return AttendanceEventOut(
            id=existing.id,
            event_id=existing.event_id,
            event_type=existing.event_type,
            previous_event_hash=existing.previous_event_hash,
            idempotency_key=existing.idempotency_key,
            server_received_at=existing.server_received_at.isoformat(),
        )

    # 5. Chain check, scoped to this device.
    last_event = (
        db.query(AttendanceEvent)
        .filter(AttendanceEvent.device_id == device.id)
        .order_by(AttendanceEvent.id.desc())
        .first()
    )
    expected_prev = last_event.event_id if last_event is not None else None
    if expected_prev != body.previous_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "previous_hash does not match chain head "
                f"(expected {expected_prev!r})"
            ),
        )

    # 6. Persist.
    event = AttendanceEvent(
        event_id=body.event_id,
        user_id=user.id,
        device_id=device.id,
        event_type=body.event_type,
        payload=payload,
        signature=body.signature_b64,
        previous_event_hash=body.previous_hash,
        idempotency_key=body.idempotency_key,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Inspect the constraint name so we report the real cause.
        # A blind 409 hides bugs like a missing NOT NULL column.
        msg = str(exc.orig).lower()
        if "uq_attendance_event_id" in msg:
            # Two requests raced on the same event_id.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="event_id already exists",
            )
        if "uq_attendance_idempotency" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency_key already used for a different event_id",
            )
        # Anything else is a schema mismatch or a bug. Return 500 so
        # the failure is visible instead of being silently reported
        # as a duplicate.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unhandled integrity error: {exc.orig}",
        )
    db.refresh(event)

    return AttendanceEventOut(
        id=event.id,
        event_id=event.event_id,
        event_type=event.event_type,
        previous_event_hash=event.previous_event_hash,
        idempotency_key=event.idempotency_key,
        server_received_at=event.server_received_at.isoformat(),
    )


@router.get("/events", response_model=list[AttendanceEventOut])
def list_events(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AttendanceEventOut]:
    rows = (
        db.query(AttendanceEvent)
        .filter(AttendanceEvent.user_id == user.id)
        .order_by(AttendanceEvent.id.asc())
        .all()
    )
    return [
        AttendanceEventOut(
            id=r.id,
            event_id=r.event_id,
            event_type=r.event_type,
            previous_event_hash=r.previous_event_hash,
            idempotency_key=r.idempotency_key,
            server_received_at=r.server_received_at.isoformat(),
        )
        for r in rows
    ]
