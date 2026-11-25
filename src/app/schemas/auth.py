from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    password: str = Field(min_length=1)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)


class ResetPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)
    otp: str = Field(min_length=1)
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)


class OtpRequest(BaseModel):
    identifier: str = Field(min_length=1)


class OtpLoginRequest(BaseModel):
    identifier: str = Field(min_length=1)
    otp: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class MessageResponse(BaseModel):
    message: str
