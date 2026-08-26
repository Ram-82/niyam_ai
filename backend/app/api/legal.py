"""/legal endpoints — read the current documents, list pending, record acceptance.

Read routes (GET /legal/documents/{doc_type}, GET /legal/pending) are
authenticated but not gated by acceptance — otherwise a firm couldn't
learn what it needs to accept.

Write route (POST /legal/accept) records an immutable acceptance row and
a parallel audit_log entry inside a single transaction.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_firm_scoped_session
from app.legal.documents import current_by_type
from app.legal.service import (
    DocumentMismatchError,
    pending_documents,
    record_acceptance,
)
from app.models.tables import AppUser


router = APIRouter(prefix="/legal", tags=["legal"])


class DocumentResponse(BaseModel):
    doc_type: str
    version: str
    content_hash: str
    effective_from: str
    content: str


class PendingDocResponse(BaseModel):
    doc_type: str
    version: str
    content_hash: str


class PendingResponse(BaseModel):
    pending: list[PendingDocResponse]


class AcceptRequest(BaseModel):
    doc_type: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(min_length=64, max_length=64)


class AcceptResponse(BaseModel):
    doc_type: str
    version: str
    content_hash: str
    remaining_pending: list[PendingDocResponse]


@router.get("/documents/{doc_type}", response_model=DocumentResponse)
def read_document(doc_type: str) -> DocumentResponse:
    """Public. The document is presented to prospective customers as the
    canonical version of the Terms / DPA — the same bytes the acceptance
    flow hashes. Rendering pre-login is intentional (marketing pages read
    from this endpoint) and gives us one source of truth: what a user
    can read at any time IS what they accept, byte-for-byte."""
    doc = current_by_type().get(doc_type)
    if doc is None:
        raise HTTPException(status_code=404, detail="unknown doc_type")
    return DocumentResponse(
        doc_type=doc.doc_type,
        version=doc.version,
        content_hash=doc.content_hash,
        effective_from=doc.effective_from,
        content=doc.content,
    )


@router.get("/pending", response_model=PendingResponse)
def list_pending(
    user: AppUser = Depends(get_current_user),
    session: Session = Depends(get_firm_scoped_session),
) -> PendingResponse:
    pending = pending_documents(session, user.firm_id)
    return PendingResponse(
        pending=[
            PendingDocResponse(
                doc_type=p.doc_type,
                version=p.version,
                content_hash=p.content_hash,
            )
            for p in pending
        ]
    )


@router.post("/accept", response_model=AcceptResponse, status_code=status.HTTP_201_CREATED)
def accept(
    payload: AcceptRequest,
    request: Request,
    user: AppUser = Depends(get_current_user),
    session: Session = Depends(get_firm_scoped_session),
) -> AcceptResponse:
    ip = _client_ip(request)
    ua: Optional[str] = request.headers.get("user-agent")
    try:
        doc = record_acceptance(
            session=session,
            firm_id=user.firm_id,
            user_id=user.id,
            doc_type=payload.doc_type,
            declared_version=payload.version,
            declared_hash=payload.content_hash,
            ip_address=ip,
            user_agent=ua,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown doc_type")
    except DocumentMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "document_mismatch", "message": str(e)},
        )
    remaining = pending_documents(session, user.firm_id)
    return AcceptResponse(
        doc_type=doc.doc_type,
        version=doc.version,
        content_hash=doc.content_hash,
        remaining_pending=[
            PendingDocResponse(
                doc_type=p.doc_type,
                version=p.version,
                content_hash=p.content_hash,
            )
            for p in remaining
        ],
    )


def _client_ip(request: Request) -> Optional[str]:
    """Best-effort client IP. Trusts X-Forwarded-For's leftmost entry when
    present — deployment behind a reverse proxy is the norm. Returns None
    for anything that isn't a parseable IPv4/IPv6 address (e.g. Starlette's
    TestClient uses ``client.host = 'testclient'``), so we don't blow up
    INSERTs into an ``INET`` column."""
    import ipaddress

    candidate: Optional[str] = None
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            candidate = first
    if candidate is None and request.client is not None:
        candidate = request.client.host
    if candidate is None:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate
