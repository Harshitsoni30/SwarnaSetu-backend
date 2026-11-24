from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.services.auth_errors import AuthError


def session_factory(database_url: str) -> sessionmaker[Session]:
    if not database_url.strip():
        raise AuthError("configuration_error", "The database is not configured.", 503)
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)
