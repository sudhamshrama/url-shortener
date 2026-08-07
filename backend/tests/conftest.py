"""Test fixtures.

Dual-backend by design:

  * No TEST_DATABASE_URL  -> in-memory SQLite. Fast, zero dependencies, runs on
                             a laptop with nothing installed. This is what keeps
                             the inner loop tight.
  * TEST_DATABASE_URL set -> real Postgres. This is what CI uses, via a service
                             container.

Running only against SQLite would be a trap: it silently tolerates things
Postgres rejects, so a green local suite could still break in production. The
point of running both is that CI catches exactly that class of divergence.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Debug endpoints must be registered before the app object is constructed, so
# this has to happen before `app.main` is imported anywhere.
os.environ.setdefault("ENABLE_DEBUG_ENDPOINTS", "true")

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import links  # noqa: E402

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
USING_POSTGRES = bool(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    if TEST_DATABASE_URL:
        eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    else:
        # StaticPool + shared cache keeps every connection pointed at the same
        # in-memory database. Without it, each connection gets its own blank
        # database and the tests fail with confusing "no such table" errors.
        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """A session wrapped in a transaction that is always rolled back.

    Each test therefore starts from an identical database regardless of what
    the previous test wrote, without paying to recreate the schema every time.
    """
    connection = engine.connect()
    transaction = connection.begin()
    # `join_transaction_mode="create_savepoint"` is what makes this work. The
    # route handlers call db.commit(), and without this the session would commit
    # the *outer* transaction — leaving nothing for the rollback below to undo,
    # so rows would leak between tests and produce spurious 409s. With it, each
    # commit resolves a SAVEPOINT nested inside our transaction, and the outer
    # rollback still discards everything.
    session = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient with the database dependency pointed at the rolled-back session."""

    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # The link cache is process-global, so a code created in one test would
    # otherwise still resolve in the next one even after its row was rolled
    # back — a false pass that would be genuinely confusing to debug.
    links.cache.clear()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def sample_url() -> str:
    return "https://example.com/a/reasonably/long/path?with=query"
