"""Filing orchestrator — routes to the right generator and persists.

Contract: `generate_filing` overwrites the single draft row for
(gstin_profile_id, period, return_type). Once status leaves 'draft'
the CA must reset it before regenerating; this prevents accidental
clobbering of a payload that was already approved/filed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import audit
from app.filings.gstr1_generator import generate_gstr1
from app.filings.gstr3b_generator import generate_gstr3b
from app.rules.default_pack import VERSION as RULE_PACK_VERSION


class FilingLocked(Exception):
    """Raised when trying to regenerate a filing that isn't in draft."""


class UnknownReturnType(Exception):
    pass


def generate_filing(
    session: Session,
    firm_id: uuid.UUID,
    gstin_profile_id: uuid.UUID,
    period: str,
    return_type: str,
    user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Generate + persist. Returns the filing_run row as a dict."""
    if return_type == "GSTR1":
        payload = generate_gstr1(session, str(gstin_profile_id), period)
    elif return_type == "GSTR3B":
        payload = generate_gstr3b(session, str(gstin_profile_id), period)
    else:
        raise UnknownReturnType(return_type)

    # Stamp generation time inside the payload — CAs will export the
    # JSON and email it around; the recipient needs to know when it was
    # built without opening the wrapping envelope.
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    existing = session.execute(
        text(
            """
            SELECT id, status FROM filing_run
            WHERE gstin_profile_id = :gid
              AND period = :p
              AND return_type = :rt
            """
        ),
        {"gid": str(gstin_profile_id), "p": period, "rt": return_type},
    ).first()

    if existing:
        if existing.status != "draft":
            raise FilingLocked(
                f"filing_run {existing.id} is {existing.status}; reset to draft first"
            )
        session.execute(
            text(
                """
                UPDATE filing_run
                   SET payload = CAST(:payload AS JSONB),
                       rule_pack_version = :rpv,
                       generated_by = :uid,
                       updated_at = now()
                 WHERE id = :id
                """
            ),
            {
                "id": str(existing.id),
                "payload": _to_json(payload),
                "rpv": RULE_PACK_VERSION,
                "uid": str(user_id) if user_id else None,
            },
        )
        filing_id = existing.id
        _audit_action = "filing.regenerated"
    else:
        row = session.execute(
            text(
                """
                INSERT INTO filing_run (
                    firm_id, gstin_profile_id, return_type, period,
                    payload, rule_pack_version, generated_by
                ) VALUES (
                    :fid, :gid, :rt, :p,
                    CAST(:payload AS JSONB), :rpv, :uid
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "gid": str(gstin_profile_id),
                "rt": return_type,
                "p": period,
                "payload": _to_json(payload),
                "rpv": RULE_PACK_VERSION,
                "uid": str(user_id) if user_id else None,
            },
        ).one()
        filing_id = row.id
        _audit_action = "filing.generated"

    audit.record(
        session=session,
        firm_id=firm_id,
        actor_user_id=user_id,
        action=_audit_action,
        entity_type="filing_run",
        entity_id=filing_id,
        metadata={
            "return_type": return_type,
            "period": period,
            "rule_pack_version": RULE_PACK_VERSION,
            "sections_covered": payload.get("_meta", {}).get("sections_covered", []),
        },
    )

    # NB: do not commit here. The dependency that opened this session
    # (get_firm_scoped_session) commits on happy exit; if we commit
    # mid-request the transaction-local ``app.current_firm_id`` GUC is
    # wiped and the fetch below returns zero rows under RLS.
    session.flush()
    return _fetch(session, filing_id)


def _to_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, separators=(",", ":"), sort_keys=False)


def _fetch(session: Session, filing_id: uuid.UUID) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT id, firm_id, gstin_profile_id, return_type, period,
                   status, payload, rule_pack_version, generated_by,
                   created_at, updated_at
              FROM filing_run WHERE id = :id
            """
        ),
        {"id": str(filing_id)},
    ).mappings().one()
    return dict(row)
