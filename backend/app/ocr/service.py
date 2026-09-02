"""OCR orchestration + feature-flag gate.

Entry points:

* :func:`get_adapter` — returns an :class:`OcrAdapter` per
  ``settings.ocr_mode``. Raises :class:`OcrDisabled` when the feature
  flag is off, so the API layer can render a 503 without leaking
  which adapter would have run.
* :func:`extract` — pure request-response: adapter runs against the
  bytes and the :class:`InvoiceExtraction` is returned. No DB writes.
* :func:`extract_and_persist` — extraction + INSERT + audit row.
* :func:`accept_extraction` — Step 4: CA approves the draft; a new
  ``Invoice`` row is created from raw (+ optional CA edits) and the
  ``ocr_extraction`` row transitions draft → accepted.
* :func:`reject_extraction` — Step 4: CA marks the draft as unusable;
  transitions draft → rejected. No Invoice row is created.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import text

from app.auth import audit
from app.config import settings
from app.db import firm_scoped_session
from app.ocr.adapter_mock import MockOcrAdapter
from app.ocr.types import (
    Direction,
    FieldConfidence,
    InvoiceExtraction,
    OcrAdapter,
    OcrDisabled,
    OcrError,
)


log = logging.getLogger("niyam.ocr.service")


def get_adapter() -> OcrAdapter:
    """Return the adapter for ``settings.ocr_mode``.

    Raises :class:`OcrDisabled` when the feature flag is off. The API
    layer maps this to HTTP 503 so the frontend can show "OCR is not
    enabled for this environment" without divulging which extractor
    would have run.
    """
    if not settings.ocr_enabled:
        raise OcrDisabled("ocr disabled (set OCR_ENABLED=1 to enable)")

    mode = (settings.ocr_mode or "mock").lower()
    if mode == "mock":
        return MockOcrAdapter()
    if mode == "pdfminer":
        # Local import so mock-mode deployments never pay pdfminer's
        # import cost (and don't require the wheel to be installed).
        from app.ocr.adapter_pdfminer import PdfMinerAdapter

        return PdfMinerAdapter()
    if mode == "tesseract":
        # Late import: pytesseract/pdf2image/Pillow are heavy and only
        # loaded when this adapter is actually selected. Missing native
        # binaries (tesseract, poppler) surface at ``.extract`` call
        # time as :class:`OcrExtractionFailed`.
        from app.ocr.adapter_tesseract import TesseractAdapter

        return TesseractAdapter()
    raise OcrError(
        f"unknown OCR_MODE={settings.ocr_mode!r} "
        "(expected 'mock', 'pdfminer', or 'tesseract')"
    )


def extract(
    *,
    content: bytes,
    filename: str,
    direction: Direction,
) -> InvoiceExtraction:
    """Run the configured adapter against the upload bytes.

    The API layer is responsible for size limits, MIME-type validation
    and rate-limiting; this function trusts its inputs.
    """
    adapter = get_adapter()  # may raise OcrDisabled
    log.info(
        "ocr.extract adapter=%s direction=%s bytes=%d filename=%s",
        adapter.adapter,
        direction,
        len(content),
        filename,
    )
    return adapter.extract(content=content, filename=filename, direction=direction)


def _extraction_to_jsonb(ext: InvoiceExtraction) -> dict:
    """Flatten the per-field ``FieldConfidence`` objects into a JSONB-ready
    dict. The stored shape mirrors the API response one-for-one so a CA
    can compare "what the machine emitted" against "what the reviewer
    saw" without a translation layer."""

    def _f(fc: FieldConfidence) -> dict:
        return {"value": fc.value, "confidence": fc.confidence}

    return {
        "supplier_gstin": _f(ext.supplier_gstin),
        "invoice_number": _f(ext.invoice_number),
        "invoice_date": _f(ext.invoice_date),
        "taxable_value_paise": _f(ext.taxable_value_paise),
        "cgst_paise": _f(ext.cgst_paise),
        "sgst_paise": _f(ext.sgst_paise),
        "igst_paise": _f(ext.igst_paise),
        "total_paise": _f(ext.total_paise),
        "hsn_sac": _f(ext.hsn_sac),
    }


class GstinProfileNotInFirm(OcrError):
    """The requested gstin_profile_id does not belong to the caller's firm.

    Raised BEFORE the OCR adapter runs so a cross-firm probe leaves no
    trace in ``ocr_extraction`` or ``audit_log``. The API layer maps
    this to HTTP 404, not 403 — we do not want to leak whether the
    profile exists in another firm.
    """


def extract_and_persist(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    direction: Direction,
    content: bytes,
    filename: str,
    user_id: Optional[str | uuid.UUID] = None,
) -> tuple[InvoiceExtraction, uuid.UUID, str, "datetime"]:
    """Run the adapter and persist a ``draft`` extraction row + audit entry.

    Returns ``(extraction, ocr_extraction_id, status, created_at)``.
    The row is inserted with ``status='draft'``; the accept / reject
    transitions land in Step 4 alongside a widened UPDATE grant.

    Raises :class:`GstinProfileNotInFirm` if ``gstin_profile_id`` is
    not visible under the caller's firm scope. This is checked BEFORE
    the adapter runs so a cross-firm probe cannot generate an audit
    row or consume adapter cost.
    """
    from datetime import datetime  # local import to keep the annotation cheap

    ext = extract(content=content, filename=filename, direction=direction)

    with firm_scoped_session(firm_id) as db:
        # Membership check. RLS scopes this SELECT to the caller's
        # firm, so an unknown or cross-firm id resolves as "no row".
        exists = db.execute(
            text("SELECT 1 FROM gstin_profile WHERE id = :i"),
            {"i": str(gstin_profile_id)},
        ).scalar()
        if exists is None:
            raise GstinProfileNotInFirm(
                f"gstin_profile {gstin_profile_id} not found under firm {firm_id}"
            )

        row = db.execute(
            text(
                """
                INSERT INTO ocr_extraction (
                    firm_id, gstin_profile_id, direction,
                    source_filename, source_content_hash, source_bytes_size,
                    adapter, adapter_version,
                    raw_extraction, overall_confidence, warnings,
                    created_by
                ) VALUES (
                    :fid, :gpid, :dir,
                    :fname, :hash, :bytes,
                    :adapter, :aver,
                    CAST(:raw AS JSONB), :conf, CAST(:warn AS JSONB),
                    :uid
                )
                RETURNING id, status, created_at
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "dir": direction,
                "fname": ext.source_filename,
                "hash": ext.source_content_hash,
                "bytes": ext.source_bytes_size,
                "adapter": ext.adapter,
                "aver": ext.adapter_version,
                "raw": json.dumps(_extraction_to_jsonb(ext)),
                "conf": ext.overall_confidence,
                "warn": json.dumps(list(ext.warnings)),
                "uid": str(user_id) if user_id else None,
            },
        ).mappings().one()
        ocr_id: uuid.UUID = row["id"]
        row_status: str = row["status"]
        row_created_at: datetime = row["created_at"]

        audit.record(
            session=db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="ocr.extracted",
            entity_type="ocr_extraction",
            entity_id=ocr_id,
            metadata={
                "adapter": ext.adapter,
                "adapter_version": ext.adapter_version,
                "direction": direction,
                "source_content_hash": ext.source_content_hash,
                "source_bytes_size": ext.source_bytes_size,
                "overall_confidence": ext.overall_confidence,
                "gstin_profile_id": str(gstin_profile_id),
            },
        )
    return ext, ocr_id, row_status, row_created_at


# ---------------------------------------------------------------------------
# Step 4: accept / reject
# ---------------------------------------------------------------------------


class ExtractionNotFound(OcrError):
    """The ocr_extraction id does not exist under the caller's firm.

    Mapped to HTTP 404 by the API — never leaks whether the row
    exists in another firm.
    """


class ExtractionAlreadyDecided(OcrError):
    """The row is not in ``draft`` status (already accepted / rejected).

    Mapped to HTTP 409 by the API — the trigger in migration 0019 is
    the ultimate guard; this Python-side check produces a nicer
    error before the transaction hits the DB.
    """


class ExtractionMissingRequiredFields(OcrError):
    """The extraction lacks one or more fields the Invoice row requires.

    Required fields: supplier_gstin (structure-valid), invoice_number,
    invoice_date, taxable_value_paise, total_paise. Mapped to HTTP 422.
    """

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"missing required fields: {missing}")
        self.missing = missing


# Fields the CA may override before accepting. Any key not in this set
# is silently ignored — a defensive posture against accidental writes.
_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "supplier_gstin",
    "invoice_number",
    "invoice_date",
    "taxable_value_paise",
    "cgst_paise",
    "sgst_paise",
    "igst_paise",
    "total_paise",
    "hsn_sac",
})


def _merged_field(raw: dict, edits: Optional[dict], key: str):
    """Return the CA-edited value if present, else the raw extraction."""
    if edits is not None and key in edits and edits[key] is not None:
        return edits[key]
    v = (raw.get(key) or {}).get("value")
    return v


def _require_int_paise(v, field_name: str) -> int:
    """Turn a str/int paise value into an int, or raise 422."""
    if v is None or v == "":
        raise ExtractionMissingRequiredFields([field_name])
    try:
        return int(v)
    except (TypeError, ValueError) as e:
        raise ExtractionMissingRequiredFields([field_name]) from e


def accept_extraction(
    *,
    firm_id: str | uuid.UUID,
    extraction_id: str | uuid.UUID,
    edited_fields: Optional[dict],
    user_id: str | uuid.UUID,
) -> uuid.UUID:
    """Materialise an ``Invoice`` row from the extraction and lock
    the ``ocr_extraction`` row as accepted.

    Returns the new ``invoice_id``. Raises:
      * :class:`ExtractionNotFound` — 404
      * :class:`ExtractionAlreadyDecided` — 409
      * :class:`ExtractionMissingRequiredFields` — 422
    """
    from datetime import date, datetime

    edits = {
        k: v for k, v in (edited_fields or {}).items() if k in _EDITABLE_FIELDS
    }

    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                "SELECT gstin_profile_id, direction, status, "
                "raw_extraction, source_content_hash "
                "FROM ocr_extraction WHERE id = :i"
            ),
            {"i": str(extraction_id)},
        ).mappings().first()
        if row is None:
            raise ExtractionNotFound(str(extraction_id))
        if row["status"] != "draft":
            raise ExtractionAlreadyDecided(
                f"extraction {extraction_id} is {row['status']}"
            )

        raw = dict(row["raw_extraction"] or {})

        # Assemble the Invoice row from raw + CA edits.
        supplier_gstin = _merged_field(raw, edits, "supplier_gstin")
        invoice_number = _merged_field(raw, edits, "invoice_number")
        invoice_date_str = _merged_field(raw, edits, "invoice_date")
        hsn = _merged_field(raw, edits, "hsn_sac")

        missing: list[str] = []
        if not supplier_gstin:
            missing.append("supplier_gstin")
        if not invoice_number:
            missing.append("invoice_number")
        if not invoice_date_str:
            missing.append("invoice_date")

        # Parse the date. Accepts ISO YYYY-MM-DD from raw extractor
        # output or a CA-supplied ISO string.
        parsed_date: Optional[date] = None
        if invoice_date_str:
            try:
                parsed_date = datetime.strptime(
                    invoice_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                missing.append("invoice_date")

        if missing:
            raise ExtractionMissingRequiredFields(missing)
        assert parsed_date is not None  # mypy: guarded above

        taxable = _require_int_paise(
            _merged_field(raw, edits, "taxable_value_paise"),
            "taxable_value_paise",
        )
        cgst = _require_int_paise(
            _merged_field(raw, edits, "cgst_paise") or 0,
            "cgst_paise",
        )
        sgst = _require_int_paise(
            _merged_field(raw, edits, "sgst_paise") or 0,
            "sgst_paise",
        )
        igst = _require_int_paise(
            _merged_field(raw, edits, "igst_paise") or 0,
            "igst_paise",
        )
        total = _require_int_paise(
            _merged_field(raw, edits, "total_paise"),
            "total_paise",
        )

        invoice_id = uuid.uuid4()
        db.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise,
                    igst_paise, total_paise, hsn_sac, content_hash
                ) VALUES (
                    :id, :fid, :gpid, 'ocr', :dir,
                    :inum, :idate, :cparty,
                    :tv, :cg, :sg,
                    :ig, :tot, :hsn, :hash
                )
                """
            ),
            {
                "id": str(invoice_id),
                "fid": str(firm_id),
                "gpid": str(row["gstin_profile_id"]),
                "dir": row["direction"],
                "inum": invoice_number,
                "idate": parsed_date,
                "cparty": supplier_gstin,
                "tv": taxable,
                "cg": cgst,
                "sg": sgst,
                "ig": igst,
                "tot": total,
                "hsn": hsn,
                # An ocr-sourced Invoice is deduped by the PDF hash +
                # profile — accepting the same PDF twice against the
                # same client would collide on invoice_content_hash_uniq.
                "hash": f"ocr:{row['source_content_hash']}",
            },
        )

        # Lock the ocr_extraction row.
        db.execute(
            text(
                """
                UPDATE ocr_extraction
                SET status = 'accepted',
                    invoice_id = :inv,
                    decided_at = now(),
                    decided_by = :uid,
                    edited_extraction = CAST(:edits AS JSONB)
                WHERE id = :i
                """
            ),
            {
                "inv": str(invoice_id),
                "uid": str(user_id),
                "edits": json.dumps(edits) if edits else None,
                "i": str(extraction_id),
            },
        )

        audit.record(
            session=db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="ocr.accepted",
            entity_type="ocr_extraction",
            entity_id=extraction_id,
            metadata={
                "invoice_id": str(invoice_id),
                "edited_field_count": len(edits),
                "edited_fields": sorted(edits.keys()),
            },
        )

    return invoice_id


def reject_extraction(
    *,
    firm_id: str | uuid.UUID,
    extraction_id: str | uuid.UUID,
    reason: Optional[str],
    user_id: str | uuid.UUID,
) -> None:
    """Mark the draft as unusable. No Invoice row is created."""
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text("SELECT status FROM ocr_extraction WHERE id = :i"),
            {"i": str(extraction_id)},
        ).mappings().first()
        if row is None:
            raise ExtractionNotFound(str(extraction_id))
        if row["status"] != "draft":
            raise ExtractionAlreadyDecided(
                f"extraction {extraction_id} is {row['status']}"
            )
        db.execute(
            text(
                """
                UPDATE ocr_extraction
                SET status = 'rejected',
                    decided_at = now(),
                    decided_by = :uid
                WHERE id = :i
                """
            ),
            {"uid": str(user_id), "i": str(extraction_id)},
        )
        audit.record(
            session=db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="ocr.rejected",
            entity_type="ocr_extraction",
            entity_id=extraction_id,
            metadata={"reason": (reason or "").strip()[:500]},
        )
