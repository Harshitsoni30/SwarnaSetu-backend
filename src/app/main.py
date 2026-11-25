from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app.api.auth import build_auth_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import (
    auth_error_handler,
    http_exception_handler,
    request_validation_handler,
    unhandled_error_handler,
)
from app.core.logging import configure_logging
from app.db.repositories import SqlAlchemyResetCodeRepository, SqlAlchemyUserRepository
from app.db.session import session_factory
from app.services.auth import AuthService, SystemClock
from app.services.auth_errors import AuthError
from app.services.google_accounts import GoogleIdentity, verify_google_id_token
from app.services.messages import SmtpSmsSender


class _GoogleTokenVerifier:
    def __init__(self, client_ids: set[str]) -> None:
        self._client_ids = client_ids

    def verify(self, token: str) -> GoogleIdentity:
        return verify_google_id_token(token, self._client_ids)


def create_app(
    settings: Settings | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved.log_level)
    application = FastAPI(title=resolved.app_name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.add_exception_handler(AuthError, auth_error_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, request_validation_handler)
    application.add_exception_handler(Exception, unhandled_error_handler)
    application.include_router(health_router)
    service = auth_service if auth_service is not None else _auth_service(resolved)
    if service is not None:
        application.include_router(build_auth_router(service))
    return application


def _auth_service(settings: Settings) -> AuthService | None:
    if not settings.database_url.strip():
        return None
    factory = session_factory(settings.database_url)
    return AuthService(
        users=SqlAlchemyUserRepository(factory),
        codes=SqlAlchemyResetCodeRepository(factory),
        secret=settings.token_secret,
        clock=SystemClock(),
        sender=SmtpSmsSender(settings),
        google=_GoogleTokenVerifier(set(settings.google_audiences())),
        environment=settings.environment,
    )


app = create_app()
