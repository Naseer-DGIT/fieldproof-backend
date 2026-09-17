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
