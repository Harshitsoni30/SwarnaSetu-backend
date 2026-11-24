import uuid
from datetime import UTC, datetime

from app.domain.users import NewUser, ResetCode, UserRecord
from app.services.auth import AuthService, Clock
from app.services.auth_errors import AuthError, DeliveryError
from app.services.google_accounts import GoogleIdentity

SECRET = "test-token-secret-value"


class MemoryUsers:
    def __init__(self) -> None:
        self.rows: list[UserRecord] = []

    def add(self, draft: NewUser) -> UserRecord:
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=draft.email,
            phone=draft.phone,
            password_hash=draft.password_hash,
            google_sub=draft.google_sub,
            created_at=datetime.now(UTC),
        )
        self.rows.append(user)
        return user

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return next((row for row in self.rows if row.id == user_id), None)

    def get_by_email(self, email: str) -> UserRecord | None:
        return next((row for row in self.rows if row.email == email), None)

    def get_by_phone(self, phone: str) -> UserRecord | None:
        return next((row for row in self.rows if row.phone == phone), None)

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None:
        return next((row for row in self.rows if row.google_sub == google_sub), None)

    def update_password(self, user_id: str, password_hash: str) -> None:
        self._replace(user_id, password_hash=password_hash, update_password=True)

    def link_google(self, user_id: str, google_sub: str) -> None:
        self._replace(user_id, google_sub=google_sub, update_google=True)

    def _replace(
        self,
        user_id: str,
        *,
        password_hash: str | None = None,
        google_sub: str | None = None,
        update_password: bool = False,
        update_google: bool = False,
    ) -> None:
        current = self.get_by_id(user_id)
        if current is None:
            raise AuthError("invalid_credentials", "The account was not found.", 401)
        updated = UserRecord(
            id=current.id,
            email=current.email,
            phone=current.phone,
            password_hash=password_hash if update_password else current.password_hash,
            google_sub=google_sub if update_google else current.google_sub,
            created_at=current.created_at,
        )
        self.rows = [updated if row.id == user_id else row for row in self.rows]


class MemoryCodes:
    def __init__(self) -> None:
        self.rows: list[ResetCode] = []

    def add(self, user_id: str, code_hash: str, expires_at: datetime, now: datetime) -> ResetCode:
        code = ResetCode(
            id=str(uuid.uuid4()),
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            used_at=None,
            created_at=now,
        )
        self.rows.append(code)
        return code

    def latest_active(self, user_id: str, now: datetime) -> ResetCode | None:
        matches = [
            row
            for row in self.rows
            if row.user_id == user_id and row.used_at is None and row.expires_at > now
        ]
        if not matches:
            return None
        return max(matches, key=lambda row: row.created_at)

    def mark_used(self, code_id: str, now: datetime) -> None:
        self.rows = [
            ResetCode(
                id=row.id,
                user_id=row.user_id,
                code_hash=row.code_hash,
                expires_at=row.expires_at,
                used_at=now if row.id == code_id else row.used_at,
                created_at=row.created_at,
            )
            for row in self.rows
        ]


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment


class RecordingSender:
    def __init__(self) -> None:
        self.emails: list[tuple[str, str]] = []
        self.texts: list[tuple[str, str]] = []

    def send_email(self, address: str, message: str) -> None:
        self.emails.append((address, message))

    def send_sms(self, phone: str, message: str) -> None:
        self.texts.append((phone, message))


class FailingSender:
    def send_email(self, address: str, message: str) -> None:
        raise DeliveryError("email")

    def send_sms(self, phone: str, message: str) -> None:
        raise DeliveryError("sms")


class FixedGoogle:
    def __init__(self, identity: GoogleIdentity) -> None:
        self.identity = identity

    def verify(self, token: str) -> GoogleIdentity:
        return self.identity


def make_service(
    clock: Clock | None = None,
    sender: RecordingSender | FailingSender | None = None,
    google: FixedGoogle | None = None,
) -> tuple[AuthService, MemoryUsers, MemoryCodes, RecordingSender | FailingSender]:
    users = MemoryUsers()
    codes = MemoryCodes()
    messages = sender if sender is not None else RecordingSender()
    identity = GoogleIdentity("sub", "person@example.com")
    verifier = google if google is not None else FixedGoogle(identity)
    service = AuthService(
        users=users,
        codes=codes,
        secret=SECRET,
        clock=clock or FrozenClock(datetime(2026, 11, 24, tzinfo=UTC)),
        sender=messages,
        google=verifier,
    )
    return service, users, codes, messages
