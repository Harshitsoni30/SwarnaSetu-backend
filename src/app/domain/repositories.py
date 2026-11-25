from datetime import datetime
from typing import Protocol

from app.domain.users import NewUser, ResetCode, UserRecord


class UserRepository(Protocol):
    def add(self, draft: NewUser) -> UserRecord: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_phone(self, phone: str) -> UserRecord | None: ...

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None: ...

    def update_password(self, user_id: str, password_hash: str) -> None: ...

    def link_google(self, user_id: str, google_sub: str) -> None: ...


class ResetCodeRepository(Protocol):
    def add(
        self,
        user_id: str,
        code_hash: str,
        expires_at: datetime,
        now: datetime,
        purpose: str = "reset",
    ) -> ResetCode: ...

    def latest_active(self, user_id: str, now: datetime, purpose: str = "reset") -> ResetCode | None: ...

    def mark_used(self, code_id: str, now: datetime) -> None: ...
