"""RQ queue setup.

Two paths:

* Prod / dev: ``settings.queue_async=True`` — ``enqueue`` returns a Job and
  a separate worker process actually runs the function.
* Tests: ``settings.queue_async=False`` — ``enqueue`` immediately calls the
  function in-process and returns a finished Job. Tests exercise the job
  code without needing a live worker.

Why RQ over Celery (recap from the README): P1 has ~2 job types, no beat
scheduling beyond a nightly cron, and RQ's operational surface (Redis + one
worker command) is a fraction of Celery's. If P3/P4 needs chord/canvas
patterns or distributed beat we migrate — but we don't front-load that
complexity today.
"""
from __future__ import annotations

from redis import Redis
from rq import Queue

from app.config import settings


QUEUE_NAME = "imports"


_redis: Redis = Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    """Return the ``imports`` queue, honoring ``settings.queue_async``."""
    return Queue(
        name=QUEUE_NAME,
        connection=_redis,
        is_async=settings.queue_async,
    )
