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
