"""CA-approval + near-miss-review gates.

The service layer calls into here BEFORE any transport call. The gate
returns the loaded delivery_request row (as a dict) so the caller does
not re-issue the same query. If the gate raises, no attempt row is
inserted and no transport is called.

Kept in its own file so future rules ("must have opt-in from client",
"must be within business hours", etc.) land here and stay testable in
isolation.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.whatsapp.types import (
    ApprovalMissing,
    DeliveryRequestLocked,
    DeliveryRequestUnknown,
    NearMissReviewMissing,
)


def load_and_validate(
    session: OrmSession,
    *,
    firm_id: str | uuid.UUID,
    delivery_request_id: str | uuid.UUID,
) -> dict[str, Any]:
    """Return the delivery_request row after validating the gate.

    Raises:
      DeliveryRequestUnknown — no row for this id under caller's firm.
      DeliveryRequestLocked — row already locked (a previous send attempt
        beat this call; caller must create a new delivery_request).
      ApprovalMissing — approved_at IS NULL.
      NearMissReviewMissing — supplier_chase with un-reviewed near-miss.
    """
    row = session.execute(
        text(
            """
            SELECT id, firm_id, client_id, gstin_profile_id, purpose,
                   narration_run_id, match_result_id,
                   whatsapp_number_snapshot, template_name,
                   template_language, approved_at, locked_at
            FROM delivery_request
            WHERE id = :id
            """
        ),
        {"id": str(delivery_request_id)},
    ).mappings().first()
    if row is None:
        raise DeliveryRequestUnknown(str(delivery_request_id))
    # RLS should have blocked cross-firm already, but belt-and-braces
    # so a mis-scoped session cannot leak: verify explicitly.
    if str(row["firm_id"]) != str(firm_id):
        raise DeliveryRequestUnknown(str(delivery_request_id))
    if row["locked_at"] is not None:
        raise DeliveryRequestLocked(str(delivery_request_id))
    if row["approved_at"] is None:
        raise ApprovalMissing(
            f"delivery_request {delivery_request_id} has not been approved"
        )
    if row["purpose"] == "supplier_chase":
        # Look up the match_result and check its context for the
        # near_miss_reviewed_at marker. If the match_result row does
        # not exist (rare — FK is RESTRICT, so this is only possible
        # if the caller passes a stale id from before the request was
        # created) we treat as un-reviewed.
        mr = session.execute(
            text(
                "SELECT context FROM match_result WHERE id = :id"
            ),
            {"id": str(row["match_result_id"])},
        ).first()
        if mr is None:
            raise NearMissReviewMissing(
                f"match_result {row['match_result_id']} not found"
            )
        context = mr[0] or {}
        if not context.get("near_miss_reviewed_at"):
            raise NearMissReviewMissing(
                f"match_result {row['match_result_id']} has no "
                f"context.near_miss_reviewed_at — CA must review the "
                f"near-miss list before a chase can be sent"
            )
    return dict(row)
