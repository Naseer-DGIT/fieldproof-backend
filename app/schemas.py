from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    tenant_id: int

    class Config:
        from_attributes = True


class DeviceRegisterRequest(BaseModel):
    public_key: str = Field(min_length=16, max_length=512)
    platform: str = Field(pattern=r"^(android|ios)$")
    # Optional, populated in S11 when attestation is wired.
    attestation_token: str | None = None


class DeviceResponse(BaseModel):
    id: int
    user_id: int
    public_key: str
    platform: str | None
    attestation_status: str
    revoked: bool

    class Config:
        from_attributes = True

class AttendanceEventIn(BaseModel):
    """Inbound attendance event.

    `payload_b64` is the base64url of the exact UTF-8 bytes that were
    signed on the device. The server verifies the signature over those
    bytes, then parses them as JSON for indexing. Sending the bytes
    instead of a parsed object removes any ambiguity about canonical
    form between Dart and Python.
    """

    event_id: str = Field(min_length=8, max_length=64)
    event_type: str = Field(pattern=r"^(check_in|check_out|break_start|break_end)$")
    payload_b64: str = Field(min_length=8, max_length=4096)
    signature_b64: str = Field(min_length=8, max_length=512)
    previous_hash: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=64)


class AttendanceEventOut(BaseModel):
    id: int
    event_id: str
    event_type: str
    previous_event_hash: str | None
    idempotency_key: str
    server_received_at: str

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------- #
# S7 — shift and leave schemas
# --------------------------------------------------------------------------- #

class ShiftCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    grace_minutes: int = Field(ge=0, le=120, default=0)
    break_minutes: int = Field(ge=0, le=480, default=0)
    overtime_threshold_minutes: int = Field(ge=0, le=240, default=0)


class ShiftResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    start_time: str
    end_time: str
    grace_minutes: int
    break_minutes: int
    overtime_threshold_minutes: int
    is_active: bool

    class Config:
        from_attributes = True


class ShiftAssignmentCreate(BaseModel):
    user_id: int
    shift_id: int
    start_date: date
    end_date: date


class ShiftAssignmentResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    shift_id: int
    start_date: date
    end_date: date

    class Config:
        from_attributes = True


class ShiftPolicyResult(BaseModel):
    """The result of comparing one event against a shift."""
    user_id: int
    for_date: date
    shift_name: str | None
    status: str  # "on_time" | "late" | "early_leave" | "absent" | "no_shift"
    first_check_in: str | None
    last_check_out: str | None
    minutes_late: int
    minutes_early_leave: int
    worked_minutes: int


# --------------------------------------------------------------------------- #
# S7 — leave schemas
# --------------------------------------------------------------------------- #

class LeaveTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    is_paid: bool = True
    annual_entitlement_days: int | None = Field(default=None, ge=0, le=365)


class LeaveTypeResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    is_paid: bool
    annual_entitlement_days: int | None
    is_active: bool

    class Config:
        from_attributes = True


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    days: float = Field(gt=0, le=365)
    reason: str | None = Field(default=None, max_length=500)


class LeaveRequestDecision(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=500)


class LeaveRequestResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    days: float
    reason: str | None
    status: str
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None

    class Config:
        from_attributes = True
