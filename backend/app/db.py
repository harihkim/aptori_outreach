from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(database_url: str | None = None) -> Engine:
    return create_engine(
        database_url or get_settings().database_url,
        future=True,
        pool_pre_ping=True,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def database_ok(database_url: str) -> bool:
    """Probe the database with a trivial round trip."""
    try:
        with make_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
