from dataclasses import dataclass

from app.services.auth_errors import AuthError
from app.services.contacts import normalize_email


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str


def identity_from_claims(claims: dict[str, object], client_ids: set[str]) -> GoogleIdentity:
    audience = claims.get("aud")
    if not client_ids or not isinstance(audience, str) or audience not in client_ids:
        raise _rejected()
    if claims.get("email_verified") is not True:
        raise AuthError("unverified_email", "The Google email address is not verified.", 401)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise _rejected()
    raw_email = claims.get("email")
    email = normalize_email(raw_email if isinstance(raw_email, str) else None)
    if email is None:
        raise _rejected()
    return GoogleIdentity(sub=subject, email=email)


def verify_google_id_token(token: str, client_ids: set[str]) -> GoogleIdentity:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            token,
            google_requests.Request(),
        )
    except ValueError as exc:
        raise _rejected() from exc
    if not isinstance(claims, dict):
        raise _rejected()
    return identity_from_claims({str(key): value for key, value in claims.items()}, client_ids)


def _rejected() -> AuthError:
    return AuthError("invalid_google_token", "The Google sign-in token was rejected.", 401)
