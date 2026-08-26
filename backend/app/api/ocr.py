"""/ocr endpoints — extract invoice fields from an uploaded PDF or photo.

P2.1 Step 2 surface:

* POST /ocr/invoice           — upload → persist draft extraction, return id.
* GET  /ocr/extractions       — list drafts for the caller's firm.
* GET  /ocr/extractions/{id}  — single draft with the frozen raw fields.

Every extraction is persisted to ``ocr_extraction`` (status='draft')
and produces an ``audit_log`` row. Acceptance-to-Invoice
(``POST /ocr/extractions/{id}/accept``) is intentionally deferred to
Step 4 — the app role has SELECT + INSERT only in Step 2, so status
transitions are impossible even by mistake.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.legal.gate import require_legal_accepted
from app.config import settings
from app.models.tables import AppUser
from app.ocr import service
from app.ocr.types import (
    Direction,
    InvoiceExtraction,
    OcrDisabled,
    OcrExtractionFailed,
    OcrUnsupportedFormat,
)


log = logging.getLogger("niyam.api.ocr")

router = APIRouter(prefix="/ocr", tags=["ocr"])


# Extensions the P2.1 pipeline is *intended* to accept. Step 1 mock
# adapter does not actually parse anything — it just hashes the bytes
# — but we still enforce the extension check at the API layer so the
# frontend upload widget and the mock share the same posture. Step 3
# will add per-adapter capability negotiation.
_ALLOWED_EXTS = frozenset({"pdf", "png", "jpg", "jpeg", "webp", "txt"})


class FieldOut(BaseModel):
    value: Optional[str]
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResp(BaseModel):
    """Response body for POST /ocr/invoice and GET /ocr/extractions/{id}.

    Mirrors :class:`app.ocr.types.InvoiceExtraction` but with fields
    flattened for a clean JSON shape the frontend can bind directly to
    the review form. The ``id`` + ``created_at`` + ``status`` fields
    come from the persisted ``ocr_extraction`` row.
    """

    id: uuid.UUID
    firm_id: uuid.UUID
    gstin_profile_id: uuid.UUID
    direction: str
    status: str
    created_at: datetime

    adapter: str
    adapter_version: str
    source_filename: str
    source_content_hash: str
    source_bytes_size: int

    supplier_gstin: FieldOut
    invoice_number: FieldOut
    invoice_date: FieldOut
    taxable_value_paise: FieldOut
    cgst_paise: FieldOut
    sgst_paise: FieldOut
    igst_paise: FieldOut
    total_paise: FieldOut
    hsn_sac: FieldOut

    overall_confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str]

    # Advisory: the review UI uses this threshold to highlight fields
    # below the bar. Included in the response so the frontend does not
    # have to re-fetch settings.
    low_confidence_threshold: float


class ExtractionListRow(BaseModel):
    """Compact row for GET /ocr/extractions.

    Everything the dashboard list view needs; skips the full
    ``raw_extraction`` payload — call GET /ocr/extractions/{id} for
    the per-field data.
    """

    id: uuid.UUID
    gstin_profile_id: uuid.UUID
    direction: str
    status: str
    adapter: str
    source_filename: str
    source_bytes_size: int
    overall_confidence: float
    created_at: datetime


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _to_response(
    ext: InvoiceExtraction,
    *,
    ocr_id: uuid.UUID,
    firm_id: uuid.UUID,
    gstin_profile_id: uuid.UUID,
    direction: str,
    status: str,
    created_at: datetime,
) -> ExtractionResp:
    def _f(fc) -> FieldOut:
        return FieldOut(value=fc.value, confidence=fc.confidence)

    return ExtractionResp(
        id=ocr_id,
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        direction=direction,
        status=status,
        created_at=created_at,
        adapter=ext.adapter,
        adapter_version=ext.adapter_version,
        source_filename=ext.source_filename,
        source_content_hash=ext.source_content_hash,
        source_bytes_size=ext.source_bytes_size,
        supplier_gstin=_f(ext.supplier_gstin),
        invoice_number=_f(ext.invoice_number),
        invoice_date=_f(ext.invoice_date),
        taxable_value_paise=_f(ext.taxable_value_paise),
        cgst_paise=_f(ext.cgst_paise),
        sgst_paise=_f(ext.sgst_paise),
        igst_paise=_f(ext.igst_paise),
        total_paise=_f(ext.total_paise),
        hsn_sac=_f(ext.hsn_sac),
        overall_confidence=ext.overall_confidence,
        warnings=list(ext.warnings),
        low_confidence_threshold=settings.ocr_low_confidence_threshold,
    )


def _row_field(raw: dict, key: str) -> FieldOut:
    """Reconstruct a FieldOut from a persisted raw_extraction JSONB dict."""
    v = raw.get(key) or {}
    return FieldOut(value=v.get("value"), confidence=float(v.get("confidence", 0.0)))


def _row_to_response(row) -> ExtractionResp:
    """Hydrate an ExtractionResp from a persisted ocr_extraction row."""
    raw = dict(row["raw_extraction"] or {})
    return ExtractionResp(
        id=row["id"],
        firm_id=row["firm_id"],
        gstin_profile_id=row["gstin_profile_id"],
        direction=row["direction"],
        status=row["status"],
        created_at=row["created_at"],
        adapter=row["adapter"],
        adapter_version=row["adapter_version"],
        source_filename=row["source_filename"],
        source_content_hash=row["source_content_hash"],
        source_bytes_size=row["source_bytes_size"],
        supplier_gstin=_row_field(raw, "supplier_gstin"),
        invoice_number=_row_field(raw, "invoice_number"),
        invoice_date=_row_field(raw, "invoice_date"),
        taxable_value_paise=_row_field(raw, "taxable_value_paise"),
        cgst_paise=_row_field(raw, "cgst_paise"),
        sgst_paise=_row_field(raw, "sgst_paise"),
        igst_paise=_row_field(raw, "igst_paise"),
        total_paise=_row_field(raw, "total_paise"),
        hsn_sac=_row_field(raw, "hsn_sac"),
        overall_confidence=float(row["overall_confidence"]),
        warnings=list(row["warnings"] or []),
        low_confidence_threshold=settings.ocr_low_confidence_threshold,
    )


@router.post(
    "/invoice",
    response_model=ExtractionResp,
    status_code=status.HTTP_201_CREATED,
)
def extract_invoice(
    gstin_profile_id: uuid.UUID = Form(...),
    direction: Literal["purchase", "sale"] = Form(...),
    file: UploadFile = File(...),
    user: AppUser = Depends(get_current_user),
    _legal: None = Depends(require_legal_accepted),
) -> ExtractionResp:
    """Extract structured fields from an uploaded invoice and persist
    a draft ``ocr_extraction`` row.

    Returns the persisted draft — the CA reviews and, once Step 4
    ships, calls ``POST /ocr/extractions/{id}/accept`` to materialise
    an ``Invoice`` row. Every attempt is audit-logged.

    ``gstin_profile_id`` scopes the extraction to a specific client's
    GSTIN; RLS on ``ocr_extraction`` (via ``firm_id``) enforces
    cross-firm isolation, and the FK to ``gstin_profile`` prevents
    posting an extraction against a GSTIN belonging to another firm
    (the FK check runs before RLS, but the FK target is itself
    firm-scoped so an out-of-firm UUID resolves to "does not exist").
    """
    ext = _extension(file.filename or "")
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported extension .{ext}; expected one of "
                f"{sorted(_ALLOWED_EXTS)}"
            ),
        )

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(content) > settings.ocr_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"upload exceeds {settings.ocr_max_upload_bytes} bytes "
                f"(got {len(content)})"
            ),
        )

    try:
        extraction, ocr_id, row_status, row_created_at = service.extract_and_persist(
            firm_id=user.firm_id,
            gstin_profile_id=gstin_profile_id,
            direction=direction,
            content=content,
            filename=file.filename or f"upload.{ext}",
            user_id=user.id,
        )
    except OcrDisabled:
        raise HTTPException(status_code=503, detail="ocr_disabled")
    except OcrUnsupportedFormat as e:
        raise HTTPException(status_code=415, detail=f"ocr_unsupported_format: {e}")
    except service.GstinProfileNotInFirm:
        # Don't disclose whether the profile exists in another firm.
        raise HTTPException(status_code=404, detail="gstin_profile not found")
    except OcrExtractionFailed as e:
        # Adapter ran but couldn't produce a usable extraction — the
        # frontend surfaces "we couldn't read this document, try again".
        raise HTTPException(status_code=422, detail=f"ocr_extraction_failed: {e}")

    log.info(
        "ocr.invoice user=%s firm=%s adapter=%s bytes=%d confidence=%.2f id=%s",
        user.id,
        user.firm_id,
        extraction.adapter,
        extraction.source_bytes_size,
        extraction.overall_confidence,
        ocr_id,
    )
    return _to_response(
        extraction,
        ocr_id=ocr_id,
        firm_id=user.firm_id,
        gstin_profile_id=gstin_profile_id,
        direction=direction,
        status=row_status,
        created_at=row_created_at,
    )


@router.get(
    "/extractions",
    response_model=list[ExtractionListRow],
)
def list_extractions(
    user: AppUser = Depends(get_current_user),
    gstin_profile_id: Optional[uuid.UUID] = None,
    status_filter: Optional[Literal["draft", "accepted", "rejected"]] = Query(
        default=None, alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    session=Depends(get_firm_scoped_session),
) -> list[ExtractionListRow]:
    """List OCR extractions for the caller's firm, newest first."""
    where = ["firm_id = :fid"]
    params: dict = {"fid": str(user.firm_id), "limit": limit}
    if gstin_profile_id is not None:
        where.append("gstin_profile_id = :gpid")
        params["gpid"] = str(gstin_profile_id)
    if status_filter is not None:
        where.append("status = :st")
        params["st"] = status_filter
    sql = (
        "SELECT id, gstin_profile_id, direction, status, adapter, "
        "source_filename, source_bytes_size, overall_confidence, created_at "
        "FROM ocr_extraction "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [
        ExtractionListRow(
            id=r["id"],
            gstin_profile_id=r["gstin_profile_id"],
            direction=r["direction"],
            status=r["status"],
            adapter=r["adapter"],
            source_filename=r["source_filename"],
            source_bytes_size=r["source_bytes_size"],
            overall_confidence=float(r["overall_confidence"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get(
    "/extractions/{extraction_id}",
    response_model=ExtractionResp,
)
def get_extraction(
    extraction_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ExtractionResp:
    """Full extraction detail — the per-field payload the review UI renders.

    RLS scopes the SELECT to the caller's firm, so an extraction that
    belongs to another firm returns 404 with no leakage.
    """
    row = session.execute(
        text(
            "SELECT id, firm_id, gstin_profile_id, direction, status, "
            "created_at, adapter, adapter_version, source_filename, "
            "source_content_hash, source_bytes_size, raw_extraction, "
            "overall_confidence, warnings "
            "FROM ocr_extraction WHERE id = :i"
        ),
        {"i": str(extraction_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="extraction not found")
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# Step 4: POST /ocr/extractions/{id}/accept and /reject
# ---------------------------------------------------------------------------


class AcceptReq(BaseModel):
    """Optional per-field CA overrides applied before the Invoice INSERT.

    Any field left absent falls back to the value in ``raw_extraction``.
    Fields with an explicit ``null`` remain null (interpreted as
    "missing" — the accept fails 422 if a required field ends up null).
    """

    edited_fields: Optional[dict[str, Optional[str]]] = None


class RejectReq(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class AcceptResp(BaseModel):
    extraction_id: uuid.UUID
    invoice_id: uuid.UUID
    status: str  # 'accepted'


class RejectResp(BaseModel):
    extraction_id: uuid.UUID
    status: str  # 'rejected'


@router.post(
    "/extractions/{extraction_id}/accept",
    response_model=AcceptResp,
)
def accept_extraction(
    extraction_id: uuid.UUID,
    payload: AcceptReq,
    user: AppUser = Depends(get_current_user),
    _legal: None = Depends(require_legal_accepted),
) -> AcceptResp:
    """Materialise an Invoice row from the extraction.

    The row transitions ``draft`` → ``accepted``. Once locked, the
    trigger from migration 0019 rejects any further UPDATE, so a
    second accept is impossible even if the API layer's own guard
    is bypassed.
    """
    try:
        invoice_id = service.accept_extraction(
            firm_id=user.firm_id,
            extraction_id=extraction_id,
            edited_fields=payload.edited_fields,
            user_id=user.id,
        )
    except service.ExtractionNotFound:
        raise HTTPException(status_code=404, detail="extraction not found")
    except service.ExtractionAlreadyDecided:
        raise HTTPException(status_code=409, detail="extraction already decided")
    except service.ExtractionMissingRequiredFields as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "ocr_missing_required_fields",
                "missing": e.missing,
            },
        )
    return AcceptResp(
        extraction_id=extraction_id,
        invoice_id=invoice_id,
        status="accepted",
    )


@router.post(
    "/extractions/{extraction_id}/reject",
    response_model=RejectResp,
)
def reject_extraction(
    extraction_id: uuid.UUID,
    payload: RejectReq,
    user: AppUser = Depends(get_current_user),
) -> RejectResp:
    """Mark the draft as unusable. No Invoice row is created; the
    reason string is stored on the audit trail."""
    try:
        service.reject_extraction(
            firm_id=user.firm_id,
            extraction_id=extraction_id,
            reason=payload.reason,
            user_id=user.id,
        )
    except service.ExtractionNotFound:
        raise HTTPException(status_code=404, detail="extraction not found")
    except service.ExtractionAlreadyDecided:
        raise HTTPException(status_code=409, detail="extraction already decided")
    return RejectResp(extraction_id=extraction_id, status="rejected")
