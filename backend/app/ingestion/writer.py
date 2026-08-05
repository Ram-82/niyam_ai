"""Single writer for GSTR-2B ingestion — reused by JSON import and GSP pulls.

Both the JSON-upload path (:mod:`app.workers.jobs`) and the GSP-pull path
(:mod:`app.gsp.service`) call these helpers so an INSERT never diverges
between the two entry points. If you find yourself copying either
function into a new file, don't — extend the callers to use these.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from app.db import firm_scoped_session
from app.ingestion.canonical import CanonicalB2BEntry


def insert_gstn_pull(
    *,
    firm_id: uuid.UUID | str,
    gstin_profile_id: uuid.UUID | str,
    period: str,
    raw_payload: dict[str, Any],
    source: str,
) -> uuid.UUID:
    """Insert one ``gstn_pull`` row and return its id.

    ``source`` is 'json_import' (uploads) or 'gsp_api' (live pulls).
    Callers must pass a period string in YYYYMM. If the payload's
    embedded rtnprd conflicts, the caller decides — this writer stores
    ``period`` verbatim.
    """
    with firm_scoped_session(firm_id) as session:
        row = session.execute(
            text(
                """
                INSERT INTO gstn_pull (
                    firm_id, gstin_profile_id, return_type, period,
                    raw_payload, source
                ) VALUES (
                    :firm_id, :gid, 'GSTR2B', :period,
                    CAST(:raw AS JSONB), :source
                )
                RETURNING id
                """
            ),
            {
                "firm_id": str(firm_id),
                "gid": str(gstin_profile_id),
                "period": period,
                "raw": json.dumps(raw_payload),
                "source": source,
            },
        )
        return row.scalar_one()


def bulk_insert_b2b_entries(
    firm_id: uuid.UUID | str,
    gstn_pull_id: uuid.UUID | str,
    entries: list[CanonicalB2BEntry],
) -> int:
    """Insert canonical b2b entries in a firm-scoped session. Returns count."""
    if not entries:
        return 0
    accepted = 0
    with firm_scoped_session(firm_id) as session:
        for e in entries:
            session.execute(
                text(
                    """
                    INSERT INTO b2b_entry (
                        firm_id, gstn_pull_id, supplier_gstin,
                        invoice_number, invoice_date, taxable_value_paise,
                        tax_paise_breakdown, itc_available, note_type,
                        ims_status, ims_action
                    ) VALUES (
                        :firm_id, :pid, :ctin,
                        :inum, :idt, :tx,
                        CAST(:tb AS JSONB), :itc,
                        CAST(:note AS b2b_note_type),
                        :ims_status, :ims_action
                    )
                    """
                ),
                {
                    "firm_id": str(firm_id),
                    "pid": str(gstn_pull_id),
                    "ctin": e.supplier_gstin,
                    "inum": e.invoice_number,
                    "idt": e.invoice_date,
                    "tx": e.taxable_value_paise,
                    "tb": json.dumps(e.tax_paise_breakdown),
                    "itc": e.itc_available,
                    "note": e.note_type,
                    "ims_status": e.ims_status,
                    "ims_action": e.ims_action,
                },
            )
            accepted += 1
    return accepted
