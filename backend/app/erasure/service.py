"""Erasure request lifecycle: create → (execute | refuse).

Kept separate from the API layer so the actual erasure workflow — which
requires admin adjudication and a policy decision on refusal grounds —
can be composed into whatever review workflow the product eventually
grows. There is no HTTP endpoint yet by design (see design doc).

Executing an erasure destroys the underlying subject key + writes an
audit_log row. It does NOT rewrite any ciphertext (there is none yet;
per-column encryption is a later per-migration effort).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import audit
from app.erasure import keys as erasure_keys


class RequestNotFound(KeyError):
    """Erasure request id does not exist in the caller's firm."""


class RequestNotPending(ValueError):
    """Erasure request has already been executed or refused."""


@dataclass(frozen=True)
class ErasureRequest:
    id: uuid.UUID
    firm_id: uuid.UUID
    subject_key_id: uuid.UUID
    status: str


def create_request(
    session: Session,
    firm_id: uuid.UUID | str,
    subject_key_id: uuid.UUID | str,
    requested_by: Optional[uuid.UUID | str],
) -> ErasureRequest:
    """Record a pending erasure request. Does not perform the erasure."""
    req_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO erasure_request (
                id, firm_id, subject_key_id, requested_by
            ) VALUES (
                CAST(:id AS UUID), CAST(:fid AS UUID),
                CAST(:sk AS UUID), CAST(:rb AS UUID)
            )
            """
        ),
        {
            "id": str(req_id),
            "fid": str(firm_id),
            "sk": str(subject_key_id),
            "rb": str(requested_by) if requested_by else None,
        },
    )
    audit.record(
        session=session,
        firm_id=firm_id,
        actor_user_id=requested_by,
        action="erasure.requested",
        entity_type="erasure_request",
        entity_id=req_id,
        metadata={"subject_key_id": str(subject_key_id)},
    )
    return ErasureRequest(
        id=req_id,
        firm_id=firm_id if isinstance(firm_id, uuid.UUID) else uuid.UUID(str(firm_id)),
        subject_key_id=(
            subject_key_id if isinstance(subject_key_id, uuid.UUID)
            else uuid.UUID(str(subject_key_id))
        ),
        status="pending",
    )


def execute_request(
    session: Session,
    firm_id: uuid.UUID | str,
    request_id: uuid.UUID | str,
    executor_user_id: Optional[uuid.UUID | str],
) -> None:
    """Destroy the subject key and mark the request executed.

    The audit_log row records the request id and the subject_key id —
    NOT any identifying content about the subject. That is deliberate:
    an erasure audit trail must not itself re-materialise the erased
    identity.
    """
    row = session.execute(
        text(
            """
            SELECT subject_key_id, status
            FROM erasure_request
            WHERE id = CAST(:id AS UUID)
              AND firm_id = CAST(:fid AS UUID)
            """
        ),
        {"id": str(request_id), "fid": str(firm_id)},
    ).mappings().first()
    if row is None:
        raise RequestNotFound(request_id)
    if row["status"] != "pending":
        raise RequestNotPending(row["status"])
    subject_key_id = row["subject_key_id"]

    erasure_keys.destroy(session, subject_key_id)
    session.execute(
        text(
            """
            UPDATE erasure_request
            SET status = 'executed', executed_at = now()
            WHERE id = CAST(:id AS UUID)
              AND status = 'pending'
            """
        ),
        {"id": str(request_id)},
    )
    audit.record(
        session=session,
        firm_id=firm_id,
        actor_user_id=executor_user_id,
        action="erasure.executed",
        entity_type="erasure_request",
        entity_id=request_id if isinstance(request_id, uuid.UUID)
        else uuid.UUID(str(request_id)),
        metadata={"subject_key_id": str(subject_key_id)},
    )


def refuse_request(
    session: Session,
    firm_id: uuid.UUID | str,
    request_id: uuid.UUID | str,
    refuser_user_id: Optional[uuid.UUID | str],
    reason: str,
) -> None:
    """Reject a pending request. Reason is required — free-form until
    counsel enumerates acceptable refusal categories (see design doc)."""
    if not reason or not reason.strip():
        raise ValueError("refusal reason is required")
    row = session.execute(
        text(
            """
            SELECT status FROM erasure_request
            WHERE id = CAST(:id AS UUID)
              AND firm_id = CAST(:fid AS UUID)
            """
        ),
        {"id": str(request_id), "fid": str(firm_id)},
    ).mappings().first()
    if row is None:
        raise RequestNotFound(request_id)
    if row["status"] != "pending":
        raise RequestNotPending(row["status"])

    session.execute(
        text(
            """
            UPDATE erasure_request
            SET status = 'refused', refusal_reason = :reason
            WHERE id = CAST(:id AS UUID)
              AND status = 'pending'
            """
        ),
        {"id": str(request_id), "reason": reason},
    )
    audit.record(
        session=session,
        firm_id=firm_id,
        actor_user_id=refuser_user_id,
        action="erasure.refused",
        entity_type="erasure_request",
        entity_id=request_id if isinstance(request_id, uuid.UUID)
        else uuid.UUID(str(request_id)),
        metadata={"reason": reason},
    )
