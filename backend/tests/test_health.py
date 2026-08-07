"""Tests for the operational endpoints.

The liveness/readiness split is a behavioural contract with Kubernetes, not an
implementation detail, so it gets tested like one.
"""

from fastapi.testclient import TestClient


def test_health_is_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_does_not_touch_the_database(client: TestClient) -> None:
    """Liveness must stay green even when the database is unreachable.

    If this test ever fails, someone has added a database check to the liveness
    probe, and a Postgres blip will now restart every pod simultaneously.
    """
    from app.database import get_db
    from app.main import app

    def broken_db():  # type: ignore[no-untyped-def]
        raise RuntimeError("database is down")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        assert client.get("/health").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_ready_reports_database_up(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "database": "up"}


def test_version_exposes_build_identity(client: TestClient) -> None:
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"version", "git_sha", "hostname"}
    # Non-empty rather than a specific value: CI injects the real SHA, and
    # asserting on the placeholder would make the test fail in the one
    # environment that matters.
    assert body["hostname"]


def test_openapi_schema_is_valid(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/api/links" in r.json()["paths"]
