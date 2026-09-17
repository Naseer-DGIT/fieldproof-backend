"""Helpers for tenant-scoped queries.

Use these instead of writing a raw query in an endpoint. A helper that
takes a `User` cannot accidentally drop the tenant filter — the filter
is inside the helper.
"""

from sqlalchemy.orm import Query, Session

from app.models import AttendanceEvent, Device, User


def tenant_user_ids(db: Session, user: User) -> Query:
    """Return a query of user ids in the same tenant as `user`.

    Callers use this as a subquery:
        .filter(AttendanceEvent.user_id.in_(tenant_user_ids(db, user)))
    """
    return db.query(User.id).filter(User.tenant_id == user.tenant_id)


def events_for_tenant(db: Session, user: User) -> Query:
    """Attendance events in the caller's tenant.

    Used by admin and supervisor endpoints. Ordinary users should use
    `events_for_self`.
    """
    return (
        db.query(AttendanceEvent)
        .join(User, AttendanceEvent.user_id == User.id)
        .filter(User.tenant_id == user.tenant_id)
    )


def events_for_self(db: Session, user: User) -> Query:
    """Attendance events for the caller only. Cross-tenant is impossible
    because the filter is on the caller's own user id, which came from
    the signed JWT."""
    return db.query(AttendanceEvent).filter(AttendanceEvent.user_id == user.id)


def devices_for_self(db: Session, user: User) -> Query:
    return db.query(Device).filter(Device.user_id == user.id)


def active_device_for_self(db: Session, user: User) -> Device | None:
    return (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .first()
    )


def active_devices_for_self(db: Session, user: User) -> list[Device]:
    return (
        db.query(Device)
        .filter(Device.user_id == user.id, Device.revoked.is_(False))
        .all()
    )
