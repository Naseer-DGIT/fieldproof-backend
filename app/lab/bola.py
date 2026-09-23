"""Lab: Broken Object Level Authorization (BOLA).

FIXED state. The vulnerable version is documented in
docs/security/s4-appsec-lab.md, Lab 2.

CWE-639, OWASP API1:2023 Broken Object Level Authorization.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.not_found import get_own_event_or_404
from app.models import User
from app.schemas import AttendanceEventOut

router = APIRouter(prefix="/lab/bola", tags=["lab"])


@router.get("/events/{event_id}", response_model=AttendanceEventOut)
def get_event_fixed(
    event_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttendanceEventOut:
    """Fetch an event owned by the caller.

    The helper resolves the event by id AND owner in a single query. A
    user reading another user's event gets 404, identical to a missing
    event.
    """
    event = get_own_event_or_404(db, user, event_id)
    return AttendanceEventOut(
        id=event.id,
        event_id=event.event_id,
        event_type=event.event_type,
        previous_event_hash=event.previous_event_hash,
        idempotency_key=event.idempotency_key,
        server_received_at=event.server_received_at.isoformat(),
    )
