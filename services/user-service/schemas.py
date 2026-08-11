from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Incoming registration payload. Validation happens here,
    before any code touches the database."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    # 12 characters minimum, in line with current NIST guidance
    # favouring length over forced character-class complexity.
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    """Outgoing user representation.

    Note what is absent: password_hash. The response schema is a
    deliberate allow-list, so a sensitive field cannot leak through
    an endpoint by accident. This is data minimisation under GDPR
    enforced in code rather than by convention.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires