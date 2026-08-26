"""Service-layer helpers for legal acceptance recording + gate evaluation.

Kept separate from the API layer so both request handlers and the
``require_legal_accepted`` dependency can share the same logic without a
round-trip through FastAPI internals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import audit
from app.legal.documents import LoadedDocument, current_by_type
from app.legal.manifest import REQUIRED_DOC_TYPES


@dataclass(frozen=True)
class PendingDoc:
    doc_type: str
    version: str
    content_hash: str


class DocumentMismatchError(Exception):
    """Raised when the client's declared (version, hash) doesn't match the
    currently-effective document. This is not a 404 — the doc_type is
    known — but the client is out of sync with the server."""


def pending_documents(session: Session, firm_id: uuid.UUID | str) -> list[PendingDoc]:
    """Return required documents the firm has NOT accepted at current hash.

    A "current hash" is the hash of the file backing the currently-effective
    version in ``app.legal.manifest``. An older acceptance row is silently
    ignored — the firm has to re-accept when the hash rolls forward.
    """
    docs = current_by_type()
    accepted_hashes = {
        row.doc_type
        for row in session.execute(
            text(
                """
                SELECT DISTINCT doc_type
                FROM legal_acceptance
                WHERE firm_id = CAST(:fid AS UUID)
                  AND content_hash = ANY(:hashes)
                """
            ),
            {
                "fid": str(firm_id),
                "hashes": [d.content_hash for d in docs.values()],
            },
        ).mappings().all()
    }
    pending: list[PendingDoc] = []
    for doc_type in REQUIRED_DOC_TYPES:
        d = docs.get(doc_type)
        if d is None:
            # Manifest disagrees with REQUIRED_DOC_TYPES — configuration bug.
            # Fail loud rather than silently pass the gate.
            raise RuntimeError(
                f"legal manifest missing required doc_type={doc_type!r}"
            )
        if doc_type not in accepted_hashes:
            pending.append(
                PendingDoc(
                    doc_type=d.doc_type,
                    version=d.version,
                    content_hash=d.content_hash,
                )
            )
    # Extra sanity: an acceptance for this doc_type MUST reference the
    # current hash to count. The DISTINCT above already scopes to current
    # hashes because we passed them in the ANY(). Double-check per-type
    # by re-running with the exact hash — cheap.
    verified: list[PendingDoc] = []
    for pd in pending:
        exists = session.execute(
            text(
                """
                SELECT 1 FROM legal_acceptance
                WHERE firm_id = CAST(:fid AS UUID)
                  AND doc_type = :dt
                  AND content_hash = :h
                LIMIT 1
                """
            ),
            {"fid": str(firm_id), "dt": pd.doc_type, "h": pd.content_hash},
        ).first()
        if not exists:
            verified.append(pd)
    return verified


def record_acceptance(
    session: Session,
    firm_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    doc_type: str,
    declared_version: str,
    declared_hash: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> LoadedDocument:
    """Insert an acceptance row after verifying declared version+hash match
    the currently-effective document, and record the parallel audit_log row.

    Raises ``DocumentMismatchError`` if the client is out of sync with the
    manifest — clients must re-fetch ``GET /legal/documents/{doc_type}``
    and try again with the fresh hash.
    """
    doc = current_by_type().get(doc_type)
    if doc is None:
        raise KeyError(doc_type)
    if declared_version != doc.version or declared_hash != doc.content_hash:
        raise DocumentMismatchError(
            f"client sent version={declared_version!r} hash={declared_hash!r} "
            f"but current is version={doc.version!r} hash={doc.content_hash!r}"
        )

    acceptance_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO legal_acceptance (
                id, firm_id, user_id, doc_type, doc_version,
                content_hash, ip_address, user_agent
            ) VALUES (
                CAST(:id AS UUID), CAST(:fid AS UUID), CAST(:uid AS UUID),
                :dt, :ver, :h, CAST(:ip AS INET), :ua
            )
            """
        ),
        {
            "id": str(acceptance_id),
            "fid": str(firm_id),
            "uid": str(user_id),
            "dt": doc.doc_type,
            "ver": doc.version,
            "h": doc.content_hash,
            "ip": ip_address,
            "ua": user_agent,
        },
    )
    audit.record(
        session=session,
        firm_id=firm_id,
        actor_user_id=user_id,
        action="legal.accepted",
        entity_type="legal_acceptance",
        entity_id=acceptance_id,
        metadata={
            "doc_type": doc.doc_type,
            "doc_version": doc.version,
            "content_hash": doc.content_hash,
        },
    )
    return doc


def has_all_accepted(session: Session, firm_id: uuid.UUID | str) -> bool:
    return not pending_documents(session, firm_id)
