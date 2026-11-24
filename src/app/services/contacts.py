import re

from app.services.auth_errors import AuthError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"\+?\d{8,15}")


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    if not stripped:
        return None
    if _EMAIL.fullmatch(stripped) is None:
        raise AuthError("validation_error", "Enter a valid email address.", 422)
    return stripped


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().replace(" ", "")
    if not stripped:
        return None
    if _PHONE.fullmatch(stripped) is None:
        raise AuthError("validation_error", "Enter a valid phone number.", 422)
    return stripped


def require_contact(email: str | None, phone: str | None) -> None:
    if email is None and phone is None:
        raise AuthError(
            "validation_error",
            "Enter an email address or a phone number.",
            422,
        )


def classify_identifier(value: str) -> tuple[str, str]:
    stripped = value.strip()
    if "@" in stripped:
        email = normalize_email(stripped)
        if email is None:
            raise AuthError("validation_error", "Enter a valid email address.", 422)
        return ("email", email)
    phone = normalize_phone(stripped)
    if phone is None:
        raise AuthError("validation_error", "Enter a valid phone number.", 422)
    return ("phone", phone)
