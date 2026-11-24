import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import PasswordResetCodeRow, UserRow
from app.domain.users import NewUser, ResetCode, UserRecord
from app.services.auth_errors import AuthError


class SqlAlchemyUserRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, draft: NewUser) -> UserRecord:
        row = UserRow(
            id=str(uuid.uuid4()),
            email=draft.email,
            phone=draft.phone,
            password_hash=draft.password_hash,
            google_sub=draft.google_sub,
            created_at=datetime.now(UTC),
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _user_record(row)

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return self._one(UserRow.id == user_id)

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._one(UserRow.email == email)

    def get_by_phone(self, phone: str) -> UserRecord | None:
        return self._one(UserRow.phone == phone)

    def get_by_google_sub(self, google_sub: str) -> UserRecord | None:
        return self._one(UserRow.google_sub == google_sub)

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._session_factory() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                raise AuthError("invalid_credentials", "The account was not found.", 401)
            row.password_hash = password_hash
            session.commit()

    def link_google(self, user_id: str, google_sub: str) -> None:
        with self._session_factory() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                raise AuthError("invalid_credentials", "The account was not found.", 401)
            row.google_sub = google_sub
            session.commit()

    def _one(self, criterion: ColumnElement[bool]) -> UserRecord | None:
        with self._session_factory() as session:
            row = session.scalar(select(UserRow).where(criterion))
            if row is None:
                return None
            return _user_record(row)


class SqlAlchemyResetCodeRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, user_id: str, code_hash: str, expires_at: datetime, now: datetime) -> ResetCode:
        row = PasswordResetCodeRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            used_at=None,
            created_at=now,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _code_record(row)

    def latest_active(self, user_id: str, now: datetime) -> ResetCode | None:
        statement = (
            select(PasswordResetCodeRow)
            .where(
                PasswordResetCodeRow.user_id == user_id,
                PasswordResetCodeRow.used_at.is_(None),
                PasswordResetCodeRow.expires_at > now,
            )
            .order_by(PasswordResetCodeRow.created_at.desc())
        )
        with self._session_factory() as session:
            row = session.scalar(statement)
            if row is None:
                return None
            return _code_record(row)

    def mark_used(self, code_id: str, now: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(PasswordResetCodeRow, code_id)
            if row is None:
                return
            row.used_at = now
            session.commit()


def _user_record(row: UserRow) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        phone=row.phone,
        password_hash=row.password_hash,
        google_sub=row.google_sub,
        created_at=row.created_at,
    )


def _code_record(row: PasswordResetCodeRow) -> ResetCode:
    return ResetCode(
        id=row.id,
        user_id=row.user_id,
        code_hash=row.code_hash,
        expires_at=row.expires_at,
        used_at=row.used_at,
        created_at=row.created_at,
    )
