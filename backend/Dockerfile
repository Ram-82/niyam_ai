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

# System deps:
#  * build-essential + libpq-dev — bcrypt/cryptography wheels + psycopg edges.
#  * libcairo2 + libpango-1.0-0 + libpangocairo-1.0-0 + libgdk-pixbuf-2.0-0 +
#    shared-mime-info — WeasyPrint's rendering stack (cairo/pango). Without
#    these the PDF renderer fails at import time, not at request time.
#  * fonts-noto-core + fonts-indic — Latin base + Devanagari/Kannada/Tamil
#    for the vernacular 2-pager narration. The template falls back through
#    DejaVu → Noto Sans → Noto Sans Devanagari/Kannada.
#  * tesseract-ocr + tesseract-ocr-eng — OCR binary + English language pack
#    for the P2.1 Step 3b scanned-invoice adapter. Additional language
#    packs (hin/kan/mar/tam) can be added later behind an OCR_LANGS build
#    arg without changing this file's shape.
#  * poppler-utils — provides ``pdftoppm``, which pdf2image shells out to
#    when rasterising each PDF page for tesseract.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-noto-core \
        fonts-indic \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy the whole project so pip's editable install can resolve the package
# layout at build time. The bind mount at runtime replaces this content but
# the .pth file installed into site-packages still points at /app, so
# imports keep working.
COPY . /app

RUN pip install --upgrade pip && pip install -e '.[dev]'

CMD ["bash"]
