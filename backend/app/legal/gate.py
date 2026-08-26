"""FastAPI dependency that blocks endpoints until legal acceptance is in place.

Used to gate the "import client data" surfaces: creating a client,
uploading purchase/sales invoices, uploading GSTR-2B. If the caller's
firm hasn't recorded an acceptance for every required document at its
current hash, we refuse with 403 and a machine-readable body the
frontend can key off to render the acceptance flow.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_firm_scoped_session
from app.legal.service import pending_documents
from app.models.tables import AppUser


LEGAL_ACCEPTANCE_REQUIRED = "legal_acceptance_required"


def require_legal_accepted(
    user: AppUser = Depends(get_current_user),
    session: Session = Depends(get_firm_scoped_session),
) -> None:
    """Raise 403 with ``pending`` list when the firm hasn't accepted all
    currently-effective documents. Returns nothing on success — callers
    take a Depends() on this for its side effect."""
    pending = pending_documents(session, user.firm_id)
    if not pending:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": LEGAL_ACCEPTANCE_REQUIRED,
            "pending": [
                {
                    "doc_type": p.doc_type,
                    "version": p.version,
                    "content_hash": p.content_hash,
                }
                for p in pending
            ],
        },
    )
