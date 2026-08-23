import logging
import uuid
from collections.abc import Generator

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """App-scoped engine and session factory; one per application instance."""

    def __init__(self, database_url: str, *, connect_timeout_seconds: int = 3) -> None:
        self.database_url = database_url
        url = make_url(database_url)
        connect_args = (
            {"connect_timeout": connect_timeout_seconds}
            if url.drivername.startswith("postgresql")
            else {}
        )
        self.engine: Engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)

    def session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def _safe_target(self) -> str:
        """Password-free host/database summary of the configured URL."""
        try:
            url = make_url(self.database_url)
        except Exception:
            return "<unparseable-url>"
        host = url.host or "<local-socket>"
        database = url.database or "<none>"
        return f"{host}/{database}"

    def probe(self) -> tuple[bool, str | None]:
        """Round-trip the engine's pool.

        Returns (healthy, diagnostic). Diagnostics are constructed only from
        the exception class name, a probe id, and a password-free URL summary;
        raw exception text is never included, so they are safe to log.
        """
        probe_id = uuid.uuid4().hex[:8]
        target = self._safe_target()
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True, None
        except Exception as error:
            classification = type(error).__name__
            logger.warning(
                "Health probe failed: %s against %s (probe %s)",
                classification,
                target,
                probe_id,
            )
            return False, f"{classification} against {target} (probe {probe_id})"

    def dispose(self) -> None:
        """Release pooled connections deterministically."""
        self.engine.dispose()
