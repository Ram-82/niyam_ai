"""FastAPI application entrypoint.

The startup hook pings Postgres and Redis. If either is unreachable we
raise loudly rather than let requests fail with obscure connection errors.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text

from app.api.admin import router as admin_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.clients import router as clients_router
from app.api.command_center import router as command_center_router
from app.api.filings import router as filings_router
from app.api.firm import router as firm_router
from app.api.gsp import router as gsp_router
from app.api.imports import router as imports_router
from app.api.invites import router as invites_router
from app.api.narrator import router as narrator_router
from app.api.reminders import router as reminders_router
from app.api.rule_packs import router as rule_packs_router
from app.api.supplier_contacts import router as supplier_contacts_router
from app.api.whatsapp import router as whatsapp_router
from app.api.workspace import router as workspace_router
from app.auth.revocation import _redis
from app.db import app_engine


log = logging.getLogger("niyam.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Ping Postgres via the app engine (SET ROLE runs, so failures here
    # surface a real config problem, not just "database is up").
    with app_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    # Ping Redis.
    _redis.ping()
    log.info("niyam.startup: postgres + redis reachable")
    yield


app = FastAPI(title="Niyam AI Backend", lifespan=_lifespan)

# Observability — JSON logs + X-Request-Id middleware. Install BEFORE
# CORS so the request-id contextvar is set for every log line, including
# CORS preflight rejections.
from app.observability import install as _install_observability
_install_observability(app)

# Expose the request-id header so browsers can read it back for bug
# reports. Extended below with Retry-After.
_EXPOSE_HEADERS = ["Retry-After", "X-Request-Id"]

# CORS — the dashboard runs on a separate origin from the API in dev
# (localhost:3000 vs localhost:8000). Without this middleware the
# browser fetch is preflighted, rejected, and the login form silently
# stays put. Override the allowlist via NIYAM_CORS_ORIGINS in prod.
_cors_origins = [
    o.strip()
    for o in os.getenv("NIYAM_CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    expose_headers=_EXPOSE_HEADERS,
)

app.include_router(auth_router)
app.include_router(invites_router)
app.include_router(imports_router)
app.include_router(command_center_router)
app.include_router(clients_router)
app.include_router(workspace_router)
app.include_router(admin_router)
app.include_router(gsp_router)
app.include_router(narrator_router)
app.include_router(whatsapp_router)
app.include_router(supplier_contacts_router)
app.include_router(filings_router)
app.include_router(audit_router)
app.include_router(reminders_router)
app.include_router(rule_packs_router)
app.include_router(calendar_router)
app.include_router(firm_router)


@app.get("/health")
def health() -> dict[str, str]:
    # Back-compat alias — /livez is the k8s-shaped probe, but this one
    # is embedded in Docker compose healthchecks and the frontend smoke.
    return {"status": "ok", "rule_pack_version": "unseeded"}


@app.get("/livez")
def livez() -> dict[str, str]:
    """Kubernetes liveness probe. Always 200 unless the process is
    unresponsive. Does NOT touch Postgres or Redis — a liveness probe
    that queries the DB will loop the pod on a transient DB outage."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> Response:
    """Kubernetes readiness probe. 200 only when Postgres and Redis
    are both reachable — a pod that can't reach either can't serve
    traffic, so k8s should stop routing to it until it recovers.

    Uses the app-role engine so the check exercises the same
    connection path the request handlers use, not the owner engine.
    """
    from sqlalchemy import text as _t
    from app.db import app_engine
    from app.auth.revocation import _redis as _rev_redis

    checks: dict[str, str] = {}

    try:
        with app_engine.connect() as conn:
            conn.execute(_t("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:  # noqa: BLE001 — probe reports any failure
        checks["postgres"] = f"error: {e.__class__.__name__}"

    try:
        _rev_redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {e.__class__.__name__}"

    healthy = all(v == "ok" for v in checks.values())
    body = json.dumps({"status": "ok" if healthy else "degraded", **checks})
    return Response(
        content=body,
        media_type="application/json",
        status_code=200 if healthy else 503,
    )
