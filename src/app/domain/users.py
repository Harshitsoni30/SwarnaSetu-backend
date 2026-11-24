from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str | None
    phone: str | None
    password_hash: str | None
    google_sub: str | None
    created_at: datetime


@dataclass(frozen=True)
class NewUser:
    email: str | None
    phone: str | None
    password_hash: str | None
    google_sub: str | None


@dataclass(frozen=True)
class ResetCode:
    id: str
    user_id: str
    code_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime
