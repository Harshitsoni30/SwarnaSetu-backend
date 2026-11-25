import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.domain.repositories import ResetCodeRepository, UserRepository
from app.domain.users import NewUser, UserRecord
from app.emails import render_welcome
from app.services.auth_errors import AuthError, DeliveryError
from app.services.contacts import (
    classify_identifier,
    normalize_email,
    normalize_phone,
    require_contact,
)
from app.services.google_accounts import GoogleIdentity
from app.services.passwords import hash_password, validate_password, verify_password
from app.services.tokens import TokenPair, issue_pair, read_token, utc_now

logger = logging.getLogger(__name__)

INVALID_LOGIN = "The email, phone, or password is incorrect."
FORGOT_MESSAGE = "If an account exists, a reset code has been sent."
LOGIN_OTP_MESSAGE = "If an account exists, a login code has been sent."
OTP_TTL = timedelta(minutes=10)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


class MessageSender(Protocol):
    def send_email(
        self,
        address: str,
        message: str,
        subject: str,
        html: str | None = None,
    ) -> None: ...

    def send_sms(self, phone: str, message: str) -> None: ...


class GoogleVerifier(Protocol):
    def verify(self, token: str) -> GoogleIdentity: ...


@dataclass
class AuthService:
    users: UserRepository
    codes: ResetCodeRepository
    secret: str
    clock: Clock
    sender: MessageSender
    google: GoogleVerifier
    environment: str = "local"

    def register(
        self,
        email: str | None,
        phone: str | None,
        password: str,
        name: str | None = None,
    ) -> TokenPair:
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        require_contact(normalized_email, normalized_phone)
        validate_password(password)
        self._reject_duplicates(normalized_email, normalized_phone)
        user = self.users.add(
            NewUser(
                email=normalized_email,
                phone=normalized_phone,
                password_hash=hash_password(password),
                google_sub=None,
                name=_clean_name(name),
            )
        )
        if normalized_email is not None:
            self._send_welcome(normalized_email, user.name)
        return issue_pair(self.secret, user.id, self.clock.now())

    def login(self, identifier: str, password: str) -> TokenPair:
        user = self._user_for_login(identifier)
        if user is None or user.password_hash is None:
            raise AuthError("invalid_credentials", INVALID_LOGIN, 401)
        if not verify_password(password, user.password_hash):
            raise AuthError("invalid_credentials", INVALID_LOGIN, 401)
        return issue_pair(self.secret, user.id, self.clock.now())

    def request_login_otp(self, identifier: str) -> None:
        user = self._find_optional(identifier)
        if user is None:
            return
        if user.phone is None:
            raise AuthError(
                "delivery_failed",
                "This account has no phone number for a login code.",
                400,
            )
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self.clock.now()
        message = f"Your SwarnaSetu login code is {code}. It expires in 10 minutes."
        self.codes.add(user.id, _hash_login_otp(self.secret, code), now + OTP_TTL, now, purpose="login")
        try:
            self.sender.send_sms(user.phone, message)
        except DeliveryError as exc:
            raise AuthError(
                "delivery_failed",
                exc.detail or "The login code could not be sent by text message.",
                503,
            ) from exc

    def login_with_otp(self, identifier: str, otp: str) -> TokenPair:
        user = self._find_optional(identifier)
        now = self.clock.now()
        code = None if user is None else self.codes.latest_active(user.id, now, purpose="login")
        expected = _hash_login_otp(self.secret, otp.strip())
        if user is None or code is None or not hmac.compare_digest(code.code_hash, expected):
            raise AuthError("invalid_otp", "The code is invalid or expired.", 401)
        self.codes.mark_used(code.id, now)
        return issue_pair(self.secret, user.id, self.clock.now())

    def refresh(self, refresh_token: str) -> TokenPair:
        user_id = read_token(self.secret, refresh_token, "refresh", self.clock.now())
        user = self.users.get_by_id(user_id)
        if user is None:
            raise AuthError("invalid_token", "The session token is invalid.", 401)
        return issue_pair(self.secret, user.id, self.clock.now())

    def forgot_password(self, identifier: str) -> str:
        user = self._find_optional(identifier)
        if user is None:
            return FORGOT_MESSAGE
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self.clock.now()
        self.codes.add(user.id, _hash_otp(self.secret, code), now + OTP_TTL, now)
        self._deliver(
            user,
            f"Your password reset code is {code}. It expires in 10 minutes.",
            "Password reset code",
        )
        return FORGOT_MESSAGE

    def reset_password(
        self,
        identifier: str,
        otp: str,
        old_password: str,
        new_password: str,
    ) -> None:
        user = self._find_optional(identifier)
        if user is None or user.password_hash is None:
            raise AuthError("password_not_set", "This account has no password yet.", 400)
        if not verify_password(old_password, user.password_hash):
            raise AuthError("password_mismatch", "The current password is incorrect.", 401)
        now = self.clock.now()
        code = self.codes.latest_active(user.id, now)
        expected = _hash_otp(self.secret, otp.strip())
        if code is None or not hmac.compare_digest(code.code_hash, expected):
            raise AuthError("invalid_otp", "The code is invalid or expired.", 401)
        validate_password(new_password)
        self.users.update_password(user.id, hash_password(new_password))
        self.codes.mark_used(code.id, now)

    def login_with_google(self, token: str) -> TokenPair:
        identity = self.google.verify(token)
        existing = self.users.get_by_google_sub(identity.sub)
        if existing is not None:
            return issue_pair(self.secret, existing.id, self.clock.now())
        by_email = self.users.get_by_email(identity.email)
        if by_email is not None:
            if by_email.google_sub not in (None, identity.sub):
                raise AuthError(
                    "google_account_conflict",
                    "That email address is linked to a different Google account.",
                    409,
                )
            self.users.link_google(by_email.id, identity.sub)
            return issue_pair(self.secret, by_email.id, self.clock.now())
        created = self.users.add(
            NewUser(
                email=identity.email,
                phone=None,
                password_hash=None,
                google_sub=identity.sub,
            )
        )
        return issue_pair(self.secret, created.id, self.clock.now())

    def _reject_duplicates(self, email: str | None, phone: str | None) -> None:
        email_taken = email is not None and self.users.get_by_email(email) is not None
        phone_taken = phone is not None and self.users.get_by_phone(phone) is not None
        if email_taken and phone_taken:
            raise AuthError(
                "identifier_taken",
                "An account already uses that email address and phone number.",
                409,
            )
        if email_taken:
            raise AuthError("identifier_taken", "An account already uses that email address.", 409)
        if phone_taken:
            raise AuthError("identifier_taken", "An account already uses that phone number.", 409)

    def _user_for_login(self, identifier: str) -> UserRecord | None:
        try:
            kind, value = classify_identifier(identifier)
        except AuthError:
            return None
        if kind == "email":
            return self.users.get_by_email(value)
        return self.users.get_by_phone(value)

    def _find_optional(self, identifier: str) -> UserRecord | None:
        return self._user_for_login(identifier)

    def _send_welcome(self, email: str, name: str | None) -> None:
        who = name or "there"
        sent = self._try_email(
            email,
            f"Hello {who}, your SwarnaSetu account has been created.",
            "Your SwarnaSetu account is ready",
            render_welcome(name),
        )
        if not sent:
            logger.error("welcome email delivery failed")

    def _deliver(self, user: UserRecord, message: str, subject: str) -> bool:
        sent = False
        if user.email is not None:
            sent = self._try_email(user.email, message, subject) or sent
        if user.phone is not None:
            sent = self._try_sms(user.phone, message) or sent
        return sent

    def _try_email(self, address: str, message: str, subject: str, html: str | None = None) -> bool:
        try:
            self.sender.send_email(address, message, subject, html)
        except DeliveryError:
            logger.error("email delivery failed")
            return False
        return True

    def _try_sms(self, phone: str, message: str) -> bool:
        try:
            self.sender.send_sms(phone, message)
        except DeliveryError:
            logger.error("code delivery failed")
            return False
        return True


def _clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 120:
        raise AuthError("invalid_name", "Enter your name.", 422)
    return cleaned


def _hash_login_otp(secret: str, code: str) -> str:
    import hashlib

    digest = hmac.new(secret.encode(), f"login:{code}".encode(), hashlib.sha256)
    return digest.hexdigest()


def _hash_otp(secret: str, code: str) -> str:
    import hashlib

    digest = hmac.new(secret.encode(), f"otp:{code}".encode(), hashlib.sha256)
    return digest.hexdigest()
