"""Observability: request-id middleware + JSON log formatter."""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.context import get_request_id, request_id_ctx
from app.observability.logging_config import JsonFormatter
from app.observability.middleware import RequestIdMiddleware


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _mk_app():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    def echo() -> dict:
        return {"request_id": get_request_id()}

    return app


def test_middleware_generates_id_when_absent() -> None:
    with TestClient(_mk_app()) as c:
        r = c.get("/echo")
        assert r.status_code == 200
        rid = r.headers.get("X-Request-Id")
        assert rid, "middleware must stamp X-Request-Id header"
        assert r.json()["request_id"] == rid


def test_middleware_honours_incoming_id() -> None:
    supplied = "req-" + uuid.uuid4().hex[:8]
    with TestClient(_mk_app()) as c:
        r = c.get("/echo", headers={"X-Request-Id": supplied})
        assert r.headers.get("X-Request-Id") == supplied
        assert r.json()["request_id"] == supplied


def test_contextvar_scoped_to_request() -> None:
    # Between requests the contextvar returns to its default ("").
    with TestClient(_mk_app()) as c:
        c.get("/echo")
        # Outside of the request scope in the test process:
        assert get_request_id() == ""


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(msg: str, **extra) -> logging.LogRecord:
    lg = logging.getLogger("niyam.test")
    r = lg.makeRecord(
        name="niyam.test",
        level=logging.INFO,
        fn="test.py",
        lno=1,
        msg=msg,
        args=(),
        exc_info=None,
        extra=extra,
    )
    return r


def test_json_formatter_shape() -> None:
    out = _format(_record("hello"))
    assert out["level"] == "INFO"
    assert out["logger"] == "niyam.test"
    assert out["message"] == "hello"
    assert out["ts"].endswith("Z")
    assert "request_id" not in out  # no request scope


def test_json_formatter_merges_extras() -> None:
    out = _format(_record("event", user_id="u1", duration_ms=42))
    assert out["user_id"] == "u1"
    assert out["duration_ms"] == 42


def test_json_formatter_includes_request_id_when_set() -> None:
    token = request_id_ctx.set("req-abc")
    try:
        out = _format(_record("scoped"))
    finally:
        request_id_ctx.reset(token)
    assert out["request_id"] == "req-abc"


def test_json_formatter_captures_exc_info() -> None:
    lg = logging.getLogger("niyam.test")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = lg.makeRecord(
            name="niyam.test",
            level=logging.ERROR,
            fn="test.py",
            lno=1,
            msg="oops",
            args=(),
            exc_info=sys.exc_info(),
        )
    out = _format(record)
    assert out["level"] == "ERROR"
    assert "ValueError: boom" in out["exc"]
