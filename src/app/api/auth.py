from fastapi import APIRouter

from app.schemas.auth import (
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services.auth import AuthService
from app.services.tokens import TokenPair

PUBLIC_AUTH_PATHS = (
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/forgot-password",
    "/auth/reset-password",
    "/auth/google",
)


def build_auth_router(service: AuthService) -> APIRouter:
    """Public account routes. Callers do not send an access token."""

    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", response_model=TokenResponse, status_code=201)
    def register(body: RegisterRequest) -> TokenResponse:
        return _tokens(
            service.register(body.email, body.phone, body.password),
        )

    @router.post("/login", response_model=TokenResponse)
    def login(body: LoginRequest) -> TokenResponse:
        return _tokens(service.login(body.identifier, body.password))

    @router.post("/refresh", response_model=TokenResponse)
    def refresh(body: RefreshRequest) -> TokenResponse:
        return _tokens(service.refresh(body.refresh_token))

    @router.post("/forgot-password", response_model=MessageResponse)
    def forgot_password(body: ForgotPasswordRequest) -> MessageResponse:
        return MessageResponse(message=service.forgot_password(body.identifier))

    @router.post("/reset-password", response_model=MessageResponse)
    def reset_password(body: ResetPasswordRequest) -> MessageResponse:
        service.reset_password(body.identifier, body.otp, body.old_password, body.new_password)
        return MessageResponse(message="Password updated.")

    @router.post("/google", response_model=TokenResponse)
    def google_login(body: GoogleLoginRequest) -> TokenResponse:
        return _tokens(service.login_with_google(body.id_token))

    return router


def _tokens(pair: TokenPair) -> TokenResponse:
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)
