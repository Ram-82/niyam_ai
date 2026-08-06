"""JSON-formatted stdlib logging.

Every log record renders as one line of JSON:
{"ts": "...Z", "level": "INFO", "logger": "...", "message": "...",
 "request_id": "...", ...extras}

Uvicorn's own loggers are re-routed through the same formatter so
"200 OK GET /health" also comes out as JSON, not as human-readable text.
The ``duration_ms`` field on request logs is a machine-friendly integer
so log aggregators can histogram without regex.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.observability.context import get_request_id


# LogRecord attributes that are structural (not user-supplied extras).
# Anything not in this set that appears on the record is treated as an
# extra field to merge into the JSON output.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            payload["request_id"] = rid
        # Attach unknown attributes as extras.
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_CONFIGURED = False


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root + uvicorn loggers.

    Idempotent — safe to call from tests and from ``install()``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = level or os.getenv("NIYAM_LOG_LEVEL", "INFO")

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(lvl)

    # Re-route uvicorn's loggers through the same handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
        lg.setLevel(lvl)

    _CONFIGURED = True
