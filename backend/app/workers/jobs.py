"""Import job functions — the code the RQ worker actually runs.

Each function is a small state machine:

    queued  ->  running  ->  completed | failed

It reads the ``import_job`` row (owner engine — the worker has no HTTP
firm scope), pins ``app.current_firm_id`` to the row's firm, parses the
uploaded file from ``settings.upload_dir/<job_id>.<ext>``, bulk-inserts
canonical rows with ON CONFLICT DO NOTHING (dedup by content_hash), and
writes counts + rejects back to the job row.

All DB writes go through a firm-scoped session so RLS applies. All
statements are on the app role (which we ``SET ROLE`` to in ``db.py``),
so the worker cannot bypass RLS.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.db import firm_scoped_session, owner_engine
from app.ingestion.canonical import CanonicalB2BEntry, CanonicalInvoice
from app.ingestion.csv_parser import ParseResult as CsvResult
from app.ingestion.csv_parser import parse_invoice_csv_bytes
from app.ingestion.errors import RejectedRow
from app.ingestion.excel_parser import parse_invoice_xlsx
from app.ingestion.gstr2b_parser import parse_gstr2b_bytes
from app.ingestion.writer import bulk_insert_b2b_entries as _shared_b2b_insert


log = logging.getLogger("niyam.workers.jobs")

# Cap rejects_json size so a runaway import doesn't blow up the row.
MAX_STORED_REJECTS = 10_000


# ---------------------------------------------------------------------------
# Public entrypoints called by RQ
# ---------------------------------------------------------------------------


def run_invoice_import(job_id: str) -> str:
    """Parse an invoice CSV/XLSX and insert canonical rows."""
    return _run(job_id, _process_invoices)


def run_gstr2b_import(job_id: str) -> str:
    """Parse a GSTR-2B JSON and insert b2b entries."""
    return _run(job_id, _process_gstr2b)


# ---------------------------------------------------------------------------
# Runner shell — state transitions, error capture
# ---------------------------------------------------------------------------


def _run(job_id: str, processor) -> str:  # noqa: ANN001
    row = _load_job(job_id)
    if row is None:
        return "missing"

    _mark_running(job_id)
    try:
        counts, rejects = processor(row)
        _mark_completed(job_id, counts=counts, rejects=rejects)
        return "completed"
    except Exception as e:
        log.exception("import job %s failed", job_id)
        _mark_failed(job_id, str(e))
        return "failed"


def _load_job(job_id: str) -> dict[str, Any] | None:
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, firm_id, gstin_profile_id, kind, filename, period
                FROM import_job
                WHERE id = :id
                """
            ),
            {"id": job_id},
        ).mappings().first()
    return dict(row) if row else None


def _mark_running(job_id: str) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE import_job "
                "SET status='running', started_at=now() "
                "WHERE id=:id"
            ),
            {"id": job_id},
        )


def _mark_completed(
    job_id: str,
    counts: dict[str, int],
    rejects: list[RejectedRow],
) -> None:
    rejects_json = [r.to_json_dict() for r in rejects[:MAX_STORED_REJECTS]]
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE import_job SET
                    status = 'completed',
                    finished_at = now(),
                    total_rows = :total,
                    accepted_rows = :accepted,
                    rejected_rows = :rejected,
                    duplicate_rows = :duplicate,
                    rejected_rows_json = CAST(:rejects AS JSONB),
                    summary = CAST(:summary AS JSONB)
                WHERE id = :id
                """
            ),
            {
                "id": job_id,
                "total": counts["total"],
                "accepted": counts["accepted"],
                "rejected": counts["rejected"],
                "duplicate": counts["duplicate"],
                "rejects": json.dumps(rejects_json),
                "summary": json.dumps(
                    {
                        **counts,
                        "rejects_truncated": len(rejects) > MAX_STORED_REJECTS,
                    }
                ),
            },
        )


def _mark_failed(job_id: str, message: str) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE import_job "
                "SET status='failed', finished_at=now(), "
                "error_message=:m "
                "WHERE id=:id"
            ),
            {"id": job_id, "m": message[:2000]},
        )


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------


def _read_upload(job_id: str) -> bytes:
    path = os.path.join(settings.upload_dir, str(job_id))
    with open(path, "rb") as f:
        return f.read()


def _process_invoices(
    job: dict[str, Any],
) -> tuple[dict[str, int], list[RejectedRow]]:
    kind = job["kind"]
    direction = "sale" if kind.startswith("sales_") else "purchase"

    data = _read_upload(str(job["id"]))
    if kind.endswith("_xlsx"):
        import io

        result: CsvResult = parse_invoice_xlsx(
            io.BytesIO(data),
            gstin_profile_id=str(job["gstin_profile_id"]),
            direction=direction,
        )
    else:
        result = parse_invoice_csv_bytes(
            data,
            gstin_profile_id=str(job["gstin_profile_id"]),
            direction=direction,
        )

    accepted, duplicate = _bulk_insert_invoices(
        firm_id=job["firm_id"],
        gstin_profile_id=job["gstin_profile_id"],
        invoices=result.invoices,
        kind=kind,
    )
    total = len(result.invoices) + len(result.rejects)
    return (
        {
            "total": total,
            "accepted": accepted,
            "rejected": len(result.rejects),
            "duplicate": duplicate,
        },
        result.rejects,
    )


def _process_gstr2b(
    job: dict[str, Any],
) -> tuple[dict[str, int], list[RejectedRow]]:
    data = _read_upload(str(job["id"]))

    # Persist the raw pull first so b2b entries have a gstn_pull_id FK.
    # Uses the same writer as the GSP-pull path — source distinguishes.
    from app.ingestion.writer import insert_gstn_pull

    pull_id = insert_gstn_pull(
        firm_id=job["firm_id"],
        gstin_profile_id=job["gstin_profile_id"],
        period=job["period"] or "000000",
        raw_payload=json.loads(data.decode("utf-8")),
        source="json_import",
    )

    parse = parse_gstr2b_bytes(data, gstn_pull_id=str(pull_id))
    accepted = _shared_b2b_insert(
        firm_id=job["firm_id"],
        gstn_pull_id=pull_id,
        entries=parse.entries,
    )
    total = parse.invoice_count
    return (
        {
            "total": total,
            "accepted": accepted,
            "rejected": len(parse.rejects),
            "duplicate": 0,  # 2B pulls dedupe by pull_id, not content_hash
            "ctin_count": parse.ctin_count,
            "detected_period": parse.period,
        },
        parse.rejects,
    )


# ---------------------------------------------------------------------------
# Bulk inserts
# ---------------------------------------------------------------------------


def _bulk_insert_invoices(
    firm_id: uuid.UUID,
    gstin_profile_id: uuid.UUID,
    invoices: list[CanonicalInvoice],
    kind: str,
) -> tuple[int, int]:
    """Insert with ON CONFLICT DO NOTHING on the (gstin, content_hash) unique.

    Returns (accepted_count, duplicate_count).
    """
    if not invoices:
        return 0, 0
    source = (
        "csv_import" if kind.endswith("_csv") else
        "csv_import" if kind.endswith("_xlsx") else  # XLSX rolls up as csv_import for source semantics
        "manual"
    )
    accepted = 0
    with firm_scoped_session(firm_id) as session:
        for inv in invoices:
            r = session.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, counterparty_gstin,
                        taxable_value_paise, cgst_paise, sgst_paise,
                        igst_paise, total_paise, hsn_sac, payload,
                        content_hash
                    ) VALUES (
                        :firm_id, :gid, :source, :direction,
                        :inum, :idt, :cp,
                        :tx, :cgst, :sgst,
                        :igst, :total, :hsn, CAST(:payload AS JSONB),
                        :hash
                    )
                    ON CONFLICT (gstin_profile_id, content_hash) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "firm_id": str(firm_id),
                    "gid": str(gstin_profile_id),
                    "source": source,
                    "direction": inv.direction,
                    "inum": inv.invoice_number,
                    "idt": inv.invoice_date,
                    "cp": inv.counterparty_gstin,
                    "tx": inv.taxable_value_paise,
                    "cgst": inv.cgst_paise,
                    "sgst": inv.sgst_paise,
                    "igst": inv.igst_paise,
                    "total": inv.total_paise,
                    "hsn": inv.hsn_sac,
                    "payload": json.dumps(inv.payload),
                    "hash": inv.content_hash(),
                },
            )
            if r.scalar_one_or_none() is not None:
                accepted += 1
    duplicate = len(invoices) - accepted
    return accepted, duplicate


# The b2b writer lives in app.ingestion.writer so the GSP-pull path
# and this JSON-upload path share one INSERT. See _process_gstr2b above.
