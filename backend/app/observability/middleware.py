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

from app.observability import metrics
from app.observability.context import request_id_ctx


_HEADER = "X-Request-Id"
_log = logging.getLogger("niyam.request")


def _matched_route(request: Request) -> str:
    """Return the matched route template (``/clients/{id}``) or a
    coarse bucket if unmatched.

    Using the raw URL as a Prometheus label is the classic cardinality
    trap — one label value per client id blows up the series count.
    FastAPI stores the matched route object in ``request.scope["route"]``
    once routing has run; we read ``.path`` off it.

    Unmatched requests (404 before routing, /docs, /openapi.json) are
    bucketed as ``__other__`` so the label set stays bounded.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return "__other__"


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
            elapsed = time.perf_counter() - start
            route = _matched_route(request)
            # Prometheus: increment request counter + observe latency
            # histogram. String status label so a future 3-digit code
            # (e.g. 421) does not need a schema change.
            metrics.http_requests_total.labels(
                method=request.method,
                route=route,
                status=str(status_code),
            ).inc()
            metrics.http_request_duration_seconds.labels(
                method=request.method,
                route=route,
            ).observe(elapsed)
            _log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": int(elapsed * 1000),
                },
            )
            request_id_ctx.reset(token)
