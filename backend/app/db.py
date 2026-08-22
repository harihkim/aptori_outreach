from collections.abc import Generator, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSessionManager:
    """App-scoped engine and session factory; one per application instance."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.engine: Engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)

    def session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def probe(self) -> tuple[bool, str | None]:
        """Round-trip the engine's pool.

        Returns (healthy, failure_reason). The failure reason may contain
        connection details — log it, never send it to clients.
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True, None
        except Exception as error:
            return False, f"{type(error).__name__}: {error}"

    def dispose(self) -> None:
        """Release pooled connections deterministically."""
        self.engine.dispose()
