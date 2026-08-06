"""ContextVar holding the current request's id.

Split out so tests can import without pulling in FastAPI or the JSON
formatter (they're heavy at import time).
"""
from __future__ import annotations

from contextvars import ContextVar


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Safe getter — returns "" when called outside a request scope."""
    return request_id_ctx.get()
