# Dev image for the Niyam backend. Not for production yet.
#
# The image installs deps at build time. docker-compose bind-mounts the host
# backend/ over /app at runtime, so edits on the host are picked up
# immediately — no rebuild needed unless pyproject.toml changes.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# Build tools for bcrypt/cryptography wheels + libpq headers for psycopg[binary]
# (binary distributes the extension but headers still help for edge cases).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the whole project so pip's editable install can resolve the package
# layout at build time. The bind mount at runtime replaces this content but
# the .pth file installed into site-packages still points at /app, so
# imports keep working.
COPY . /app

RUN pip install --upgrade pip && pip install -e '.[dev]'

CMD ["bash"]
