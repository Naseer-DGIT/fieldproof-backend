"""FieldProof — SQLAlchemy models (S0 baseline).

Covers the MVP entities needed for Sprint 1-7. Later sprints add Shift,
LeaveRequest, LOPRecord, SecurityEvent, AIQuery, etc. via new migrations.

Naming rules:
- Table names are plural snake_case.
- Every tenant-scoped table has a tenant_id FK (indexed) for isolation.
- Every attendance event carries signature + previous_event_hash (tamper-evident).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Tenant & identity
# --------------------------------------------------------------------------- #

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    # role: employee | supervisor | hr_ops | security_admin | sys_admin
    role = Column(String(32), nullable=False, default="employee")
    # Team membership for supervisors. Nullable for employees and for
    # roles that do not use team scope. A "team" is an integer scoped
    # inside a tenant; a proper Team model arrives in S7.
    team_id = Column(Integer, nullable=True, index=True)
    # Incremented whenever role, tenant_id, or is_active changes.
    # Included in the JWT as `rv` and checked on every request.
    # See ADR-0003.
    role_version = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant", back_populates="users")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    events = relationship("AttendanceEvent", back_populates="user")


# --------------------------------------------------------------------------- #
# Device trust
# --------------------------------------------------------------------------- #

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    # Device public key — used to verify signatures on attendance events.
    public_key = Column(String, nullable=False)
    # attestation_status: PENDING | VERIFIED | FAILED | REVOKED
    attestation_status = Column(String(16), nullable=False, default="PENDING")
    # Platform hint: android | ios
    platform = Column(String(16), nullable=True)
    # Optional: last integrity verdict from Play Integrity / App Attest.
    last_integrity_verdict = Column(String(32), nullable=True)
    revoked = Column(Boolean, nullable=False, default=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="devices")
    events = relationship("AttendanceEvent", back_populates="device")


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #

class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_attendance_event_id"),
        UniqueConstraint("idempotency_key", name="uq_attendance_idempotency"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="RESTRICT"),
                       nullable=False)
    # event_type: check_in | check_out | break_start | break_end
    event_type = Column(String(32), nullable=False)
    # payload: GPS, site_id, timestamps, mock-location flags, etc.
    payload = Column(JSON, nullable=False)
    # Base64 Ed25519 signature over (canonical payload || previous_hash)
    signature = Column(String, nullable=False)
    # Hash of the previous event for this user — tamper-evident chain.
    previous_event_hash = Column(String, nullable=True)
    # Client-supplied, unique per event — replay defense.
    idempotency_key = Column(String(64), nullable=False)
    # Server clock — the authoritative time.
    server_received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="events")
    device = relationship("Device", back_populates="events")


class AuthorizationEvent(Base):
    """Audit trail for denied requests.

    One row per 401, 403, or 404-not-403 response. No PII, no request
    body, no headers. See ADR-0003 and DATA_CLASSIFICATION.md.

    `reason` is the human-readable `detail` from the HTTPException.
    `user_id` and `tenant_id` are null when the caller was not
    authenticated (401).
    """

    __tablename__ = "authorization_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    status_code = Column(Integer, nullable=False)
    reason = Column(String(128), nullable=False)
    method = Column(String(8), nullable=False)
    endpoint = Column(String(128), nullable=False)
    # Hash chain. `previous_hash` is the `self_hash` of the row before
    # this one. The first row uses "GENESIS". `self_hash` is
    # SHA-256(previous_hash || canonical fields). See app/services/audit.py.
    previous_hash = Column(String(64), nullable=False, default="GENESIS")
    self_hash = Column(String(64), nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


# --------------------------------------------------------------------------- #
# S7 — Shift and leave models
# --------------------------------------------------------------------------- #

class Shift(Base):
    """A shift template within a tenant.

    Example: "Day", "Night", "General 9-6". A shift defines the expected
    start and end of work, the grace window, and the break policy.

    Time fields are stored as "HH:MM" strings. They are local wall-clock
    times. The tenant's timezone is applied when comparing against
    event timestamps.
    """

    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    name = Column(String(64), nullable=False)
    start_time = Column(String(5), nullable=False)   # "09:00"
    end_time = Column(String(5), nullable=False)     # "18:00"
    # Grace period after start_time before a check-in is "late"
    grace_minutes = Column(Integer, nullable=False, default=0)
    # Expected unpaid break duration in minutes
    break_minutes = Column(Integer, nullable=False, default=0)
    # Overtime is time beyond this many minutes after end_time
    overtime_threshold_minutes = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_shifts_tenant_name"),
    )


class ShiftAssignment(Base):
    """Assignment of a user to a shift for a date range.

    The date range is inclusive on both ends: `start_date <= d <= end_date`.
    A user may have at most one active shift at any given date. Overlaps
    are rejected at insert time by the service layer.
    """

    __tablename__ = "shift_assignments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="CASCADE"),
                      nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LeaveType(Base):
    """A category of leave within a tenant.

    Example: "Casual", "Sick", "Earned". Each type has an optional
    annual entitlement and a flag for whether it is paid.
    """

    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    name = Column(String(64), nullable=False)
    is_paid = Column(Boolean, nullable=False, default=True)
    # Days per year. Null means no fixed entitlement.
    annual_entitlement_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_leave_types_tenant_name"),
    )


class LeaveRequest(Base):
    """A request for leave by an employee.

    Status lifecycle: pending → approved | rejected | cancelled.
    Only the requester may cancel. Only a supervisor or HR may approve
    or reject.
    """

    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id", ondelete="RESTRICT"),
                           nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    # Full days or half days. Stored as a float to allow 0.5.
    days = Column(Numeric(5, 2), nullable=False)
    reason = Column(String(500), nullable=True)
    # status: pending | approved | rejected | cancelled
    status = Column(String(16), nullable=False, default="pending", index=True)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LOPRecord(Base):
    """Loss of Pay record.

    Generated by a monthly job that compares approved attendance against
    the assigned shift. LOP days are unpaid and feed the payroll export.

    `source` names the reason: "unapproved_absence", "late_arrival",
    "insufficient_hours", "manual".
    """

    __tablename__ = "lop_records"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    for_date = Column(Date, nullable=False, index=True)
    days = Column(Numeric(5, 2), nullable=False)
    source = Column(String(32), nullable=False)
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "for_date", "source", name="uq_lop_user_date_source"),
    )
