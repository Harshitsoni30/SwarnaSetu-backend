import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.domain.repositories import ResetCodeRepository, UserRepository
from app.domain.users import NewUser, UserRecord
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
OTP_TTL = timedelta(minutes=10)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


class MessageSender(Protocol):
    def send_email(self, address: str, message: str) -> None: ...

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

    def register(self, email: str | None, phone: str | None, password: str) -> TokenPair:
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
            )
        )
        return issue_pair(self.secret, user.id, self.clock.now())

    def login(self, identifier: str, password: str) -> TokenPair:
        user = self._user_for_login(identifier)
        if user is None or user.password_hash is None:
            raise AuthError("invalid_credentials", INVALID_LOGIN, 401)
        if not verify_password(password, user.password_hash):
            raise AuthError("invalid_credentials", INVALID_LOGIN, 401)
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
        self._deliver(user, f"Your password reset code is {code}. It expires in 10 minutes.")
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
        if email is not None and self.users.get_by_email(email) is not None:
            raise AuthError("identifier_taken", "An account already uses that email address.", 409)
        if phone is not None and self.users.get_by_phone(phone) is not None:
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

    def _deliver(self, user: UserRecord, message: str) -> None:
        if user.email is not None:
            self._try_email(user.email, message)
        if user.phone is not None:
            self._try_sms(user.phone, message)

    def _try_email(self, address: str, message: str) -> None:
        try:
            self.sender.send_email(address, message)
        except DeliveryError:
            logger.error("reset code delivery failed")

    def _try_sms(self, phone: str, message: str) -> None:
        try:
            self.sender.send_sms(phone, message)
        except DeliveryError:
            logger.error("reset code delivery failed")


def _hash_otp(secret: str, code: str) -> str:
    import hashlib

    digest = hmac.new(secret.encode(), f"otp:{code}".encode(), hashlib.sha256)
    return digest.hexdigest()
