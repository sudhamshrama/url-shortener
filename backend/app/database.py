"""Database engine, session factory, and the FastAPI dependency that hands out
sessions.

Design note: this uses *synchronous*
SQLAlchemy, and the route handlers are declared with plain `def` rather than
`async def`. FastAPI runs plain `def` handlers in a worker threadpool, so a
blocking database call never stalls the event loop. The failure mode we are
avoiding is the common one: `async def` handlers that call a blocking driver,
which serialises every request in the process and produces latency that looks
inexplicable under load.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    # Checks the connection is alive before handing it out. Without this, a
    # Postgres restart (or a StatefulSet pod being rescheduled, which will
    # happen in Kubernetes) leaves stale connections in the pool and the next
    # few requests fail for no visible reason.
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Yield a session and guarantee it is returned to the pool.

    Connection pools are finite. A handler that raises without closing its
    session leaks a connection, and the symptom — the app hanging once it has
    served exactly `pool_size + max_overflow` requests — is memorably annoying
    to diagnose. The try/finally is what prevents it.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
