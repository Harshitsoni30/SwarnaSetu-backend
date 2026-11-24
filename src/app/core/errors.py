import logging
from collections.abc import Sequence
from typing import TypedDict

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.auth_errors import AuthError

logger = logging.getLogger(__name__)


class ErrorBody(TypedDict):
    code: str
    message: str
    details: dict[str, object]


def error_body(
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> ErrorBody:
    return {"code": code, "message": message, "details": details or {}}


def sanitize_validation_errors(errors: Sequence[object]) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        sanitized.append(
            {
                "loc": _location(error.get("loc")),
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return sanitized


def _location(value: object) -> list[str | int]:
    if not isinstance(value, tuple):
        return []
    parts: list[str | int] = []
    for part in value:
        if isinstance(part, str | int):
            parts.append(part)
        else:
            parts.append(str(part))
    return parts


async def auth_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AuthError):
        return await unhandled_error_handler(request, exc)
    logger.info("auth error %s %s %s", exc.code, request.method, request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return await unhandled_error_handler(request, exc)

    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    logger.info(
        "http error %s %s %s",
        exc.status_code,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body("http_error", message),
    )


async def request_validation_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return await unhandled_error_handler(request, exc)

    logger.info("request validation failed %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            {"errors": sanitize_validation_errors(exc.errors())},
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled error %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "An unexpected error occurred."),
    )
