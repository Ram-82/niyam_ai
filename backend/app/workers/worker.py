"""RQ worker entrypoint. Run with ``python -m app.workers.worker``.

The worker connects to the same Redis as the API, listens on the
``imports`` queue, and executes jobs registered in ``app.workers.jobs``.
"""
from __future__ import annotations

import logging

from rq import Worker

from app.workers.queue import _redis, QUEUE_NAME


logging.basicConfig(level=logging.INFO)


def main() -> None:
    worker = Worker([QUEUE_NAME], connection=_redis)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
