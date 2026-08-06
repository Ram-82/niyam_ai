"""/livez + /readyz probe shape.

Deliberately unit-scoped: /livez must NEVER touch the DB or Redis, and
/readyz must return 503 when either dependency is unreachable. That
second property is exercised by monkeypatching the Redis client, since
we can't cleanly stop the real one from a pytest fixture without
affecting other tests running in the same DB.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_livez_returns_ok_without_touching_db(fastapi_app) -> None:
    with TestClient(fastapi_app) as c:
        r = c.get("/livez")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ok_when_all_dependencies_reachable(fastapi_app) -> None:
    with TestClient(fastapi_app) as c:
        r = c.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"


def test_readyz_503_when_redis_ping_fails(fastapi_app, monkeypatch) -> None:
    # Redis-py's client uses __slots__-style attributes for some methods;
    # patch the whole module-level singleton with a stub whose .ping raises.
    # The endpoint re-imports the attribute inside the handler, so a module
    # attribute swap propagates without a reload.
    from app.auth import revocation

    class _BoomRedis:
        def ping(self):
            raise ConnectionError("redis unreachable")

    monkeypatch.setattr(revocation, "_redis", _BoomRedis())

    with TestClient(fastapi_app) as c:
        r = c.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "ok"
    assert body["redis"].startswith("error:")


def test_health_alias_still_works(fastapi_app) -> None:
    """gsp-mock's Docker healthcheck + the frontend smoke both hit /health.
    Keep it responding 200 so nothing breaks."""
    with TestClient(fastapi_app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
