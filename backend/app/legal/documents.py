"""Load and hash the versioned legal documents at import time.

We compute the SHA-256 of each file once, at process start, and cache it.
A running process therefore has a single source of truth for
"the currently-effective document hash for doc_type=X". If a document
file changes on disk, the process needs a restart to pick it up — this
is deliberate: an acceptance row records the hash the process was
serving at accept time, and we do not want two web workers to disagree
on which hash counts as "current" mid-request.
"""
from __future__ import annotations

import functools
import hashlib
import os
from dataclasses import dataclass
from typing import Mapping

from app.legal.manifest import CURRENT_DOCUMENTS, LegalDocument


DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "documents")


@dataclass(frozen=True)
class LoadedDocument:
    doc_type: str
    version: str
    content_hash: str    # sha256, lowercase hex.
    content: str         # utf-8 text as served to the user.
    effective_from: str
    notes: str


def _load_one(doc: LegalDocument) -> LoadedDocument:
    path = os.path.join(DOCUMENTS_DIR, doc.filename)
    with open(path, "rb") as f:
        raw = f.read()
    h = hashlib.sha256(raw).hexdigest()
    return LoadedDocument(
        doc_type=doc.doc_type,
        version=doc.version,
        content_hash=h,
        content=raw.decode("utf-8"),
        effective_from=doc.effective_from,
        notes=doc.notes,
    )


@functools.lru_cache(maxsize=1)
def current_by_type() -> Mapping[str, LoadedDocument]:
    """Return a mapping doc_type -> LoadedDocument, memoised for process life."""
    return {d.doc_type: _load_one(d) for d in CURRENT_DOCUMENTS}


def current(doc_type: str) -> LoadedDocument | None:
    return current_by_type().get(doc_type)
