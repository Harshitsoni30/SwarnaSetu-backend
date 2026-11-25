import re

from app.services.auth_errors import AuthError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NON_DIGITS = re.compile(r"\D")


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
    digits = _NON_DIGITS.sub("", value)
    if not digits:
        return None
    local = _local_digits(digits)
    if not 8 <= len(local) <= 15:
        raise AuthError("validation_error", "Enter a valid phone number.", 422)
    if len(local) == 10:
        return local
    if value.strip().startswith("+"):
        return f"+{digits}"
    return digits


def phone_match_keys(phone: str) -> tuple[str, ...]:
    """Forms that should count as the same stored phone number."""

    digits = _NON_DIGITS.sub("", phone)
    local = _local_digits(digits)
    keys = {phone, digits, f"+{digits}", local, f"+{local}"}
    if len(local) == 10:
        keys.update({f"91{local}", f"+91{local}", f"0{local}"})
    return tuple(sorted(keys))


def _local_digits(digits: str) -> str:
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


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
