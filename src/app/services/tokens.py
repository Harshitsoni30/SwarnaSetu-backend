import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.services.auth_errors import AuthError

TokenType = Literal["access", "refresh"]
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def issue_token(
    secret: str,
    user_id: str,
    token_type: TokenType,
    ttl: timedelta,
    now: datetime,
) -> str:
    _require_secret(secret)
    expires_at = int((now + ttl).timestamp())
    body = _encode({"sub": user_id, "typ": token_type, "exp": expires_at})
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def issue_pair(secret: str, user_id: str, now: datetime) -> TokenPair:
    return TokenPair(
        access_token=issue_token(secret, user_id, "access", ACCESS_TTL, now),
        refresh_token=issue_token(secret, user_id, "refresh", REFRESH_TTL, now),
    )


def read_token(secret: str, token: str, expected_type: TokenType, now: datetime) -> str:
    _require_secret(secret)
    body, separator, signature = token.partition(".")
    if not separator or not signature:
        raise _invalid_token()
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise _invalid_token()
    payload = _decode(body)
    if payload.get("typ") != expected_type:
        raise _invalid_token()
    expires_at = payload.get("exp")
    subject = payload.get("sub")
    if not isinstance(expires_at, int) or not isinstance(subject, str) or not subject:
        raise _invalid_token()
    if expires_at <= int(now.timestamp()):
        raise _invalid_token()
    return subject


def _require_secret(secret: str) -> None:
    if not secret.strip():
        raise AuthError("configuration_error", "The token secret is not configured.", 503)


def _invalid_token() -> AuthError:
    return AuthError("invalid_token", "The session token is invalid.", 401)


def _encode(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(body: str) -> dict[str, object]:
    padding = "=" * (-len(body) % 4)
    try:
        parsed = json.loads(base64.urlsafe_b64decode(body + padding))
    except (json.JSONDecodeError, ValueError) as exc:
        raise _invalid_token() from exc
    if not isinstance(parsed, dict):
        raise _invalid_token()
    return {str(key): value for key, value in parsed.items()}


def utc_now() -> datetime:
    return datetime.now(UTC)
