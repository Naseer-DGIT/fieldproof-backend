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
    DateTime,
    ForeignKey,
    Integer,
    JSON,
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
        UniqueConstraint("idempotency_key", name="uq_attendance_idempotency"),
    )

    id = Column(Integer, primary_key=True)
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
