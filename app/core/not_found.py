"""404-not-403 helpers.

When a caller is not allowed to see a resource, respond as if it does
not exist. This prevents enumeration: an attacker cannot distinguish
"event 42 is not mine" from "event 42 does not exist" by watching the
status code, the response body, or the timing.

The critical rule: the ownership filter is *inside* the same query as
the id filter. Fetching first and checking ownership afterward can leak
existence via timing differences or via an unrelated error that fires
before the check.
"""

from fastapi import HTTPException, status

from app.models import AttendanceEvent, User


def get_own_event_or_404(
    db,
    user: User,
    event_id: str,
) -> AttendanceEvent:
    """Return the caller's attendance event, or raise 404.

    Raises 404 whether the event does not exist, belongs to another
    user, or belongs to another tenant. The response is identical in
    all three cases.
    """
    event = (
        db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.event_id == event_id,
            AttendanceEvent.user_id == user.id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return event


def get_team_event_or_404(
    db,
    user: User,
    event_id: str,
) -> AttendanceEvent:
    """Return an event in the caller's team, or raise 404.

    The caller must be a supervisor with `team_id` set. The endpoint
    checks the role and team; this helper only resolves the resource.

    Returns 404 whether the event does not exist, belongs to another
    team, or belongs to another tenant. Single query, single message.
    """
    event = (
        db.query(AttendanceEvent)
        .join(User, AttendanceEvent.user_id == User.id)
        .filter(
            AttendanceEvent.event_id == event_id,
            User.tenant_id == user.tenant_id,
            User.team_id == user.team_id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return event
