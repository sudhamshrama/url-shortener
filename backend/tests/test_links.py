"""Tests for link creation, lookup, and redirect."""

from fastapi.testclient import TestClient


def test_create_link_returns_201_and_a_code(client: TestClient, sample_url: str) -> None:
    r = client.post("/api/links", json={"target_url": sample_url})
    assert r.status_code == 201
    body = r.json()
    assert len(body["code"]) == 7
    assert body["target_url"] == sample_url
    assert body["hit_count"] == 0
    assert body["short_url"].endswith(body["code"])


def test_create_link_with_custom_code(client: TestClient, sample_url: str) -> None:
    r = client.post("/api/links", json={"target_url": sample_url, "custom_code": "mylink"})
    assert r.status_code == 201
    assert r.json()["code"] == "mylink"


def test_duplicate_custom_code_conflicts(client: TestClient, sample_url: str) -> None:
    client.post("/api/links", json={"target_url": sample_url, "custom_code": "taken"})
    r = client.post("/api/links", json={"target_url": sample_url, "custom_code": "taken"})
    assert r.status_code == 409


def test_rejects_non_http_schemes(client: TestClient) -> None:
    """An open redirector that emits javascript: URLs is an XSS vector."""
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>"):
        r = client.post("/api/links", json={"target_url": bad})
        assert r.status_code == 422, f"{bad} should have been rejected"


def test_rejects_non_alphanumeric_custom_code(client: TestClient, sample_url: str) -> None:
    r = client.post("/api/links", json={"target_url": sample_url, "custom_code": "../../etc"})
    assert r.status_code == 422


def test_redirect_sends_307_to_target(client: TestClient, sample_url: str) -> None:
    code = client.post("/api/links", json={"target_url": sample_url}).json()["code"]

    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == sample_url


def test_redirect_increments_hit_count(client: TestClient, sample_url: str) -> None:
    code = client.post("/api/links", json={"target_url": sample_url}).json()["code"]

    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)

    stats = client.get(f"/api/links/{code}").json()
    assert stats["hit_count"] == 3
    assert stats["last_hit_at"] is not None


def test_unknown_code_is_404(client: TestClient) -> None:
    assert client.get("/nosuch", follow_redirects=False).status_code == 404
    assert client.get("/api/links/nosuch").status_code == 404


def test_operational_routes_are_not_shadowed_by_the_catchall(client: TestClient) -> None:
    """Regression guard for the route-ordering bug.

    `/{code}` is registered last precisely so it cannot swallow these. If
    someone reorders the routers in main.py, this is the test that catches it —
    and the symptom without it would be a 404 on /health, which Kubernetes
    would read as a dead pod.
    """
    for path in ("/health", "/ready", "/version", "/docs", "/openapi.json"):
        assert client.get(path).status_code == 200, f"{path} was shadowed"


def test_second_lookup_is_served_from_cache(client: TestClient, sample_url: str) -> None:
    from app.routes import links

    code = client.post("/api/links", json={"target_url": sample_url}).json()["code"]
    before = links.cache.hits

    client.get(f"/{code}", follow_redirects=False)

    assert links.cache.hits == before + 1
