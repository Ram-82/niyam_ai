"""Request-id middleware for FastAPI/Starlette.

Extracts an existing ``X-Request-Id`` header (so an ingress or a caller
that already stamped one is honoured) or generates a fresh UUID4. Pins
it into ``request_id_ctx`` for the duration of the request so log lines
and audit rows can pick it up. Echoes it back on the response so a
client can quote the id in a bug report.
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import request_id_ctx


_HEADER = "X-Request-Id"
_log = logging.getLogger("niyam.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(_HEADER) or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_HEADER] = rid
            return response
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            _log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": elapsed_ms,
                },
            )
            request_id_ctx.reset(token)
