"""Cross-cutting observability primitives.

Exports:
* ``request_id_ctx`` — contextvar holding the current request's id.
* ``get_request_id()`` — safe getter returning "" when outside a request.
* ``install(app)``  — one-call wire-up: middleware + logging config.
"""
from __future__ import annotations

from app.observability.context import get_request_id, request_id_ctx
from app.observability.logging_config import configure_logging
from app.observability.middleware import RequestIdMiddleware


def install(app) -> None:  # noqa: ANN001 — FastAPI instance
    """Install request-id middleware and swap the log formatter for JSON.

    Idempotent — safe to call multiple times (tests re-import app).
    """
    configure_logging()
    # Middleware order matters: request-id runs first so log lines from
    # downstream middleware carry the id too.
    app.add_middleware(RequestIdMiddleware)


__all__ = [
    "RequestIdMiddleware",
    "configure_logging",
    "get_request_id",
    "install",
    "request_id_ctx",
]
