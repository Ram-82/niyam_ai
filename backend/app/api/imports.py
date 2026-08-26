"""/imports endpoints — upload files, enqueue jobs, check status, download rejects.

Every upload:
1. Writes the file to ``settings.upload_dir/<job_id>`` (shared volume between
   the API and the worker containers).
2. Inserts an ``import_job`` row via the firm-scoped session (RLS applies).
3. Enqueues the RQ job — or, when ``settings.queue_async=False`` (tests),
   runs it in-process immediately.
4. Returns ``202 Accepted`` with the job id.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select, text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.auth import audit
from app.legal.gate import require_legal_accepted
from app.config import settings
from app.db import firm_scoped_session
from app.ingestion.errors import rejects_to_csv
from app.models.tables import AppUser, ImportJob
from app.workers import jobs as job_functions
from app.workers.queue import get_queue


router = APIRouter(prefix="/imports", tags=["imports"])


ALLOWED_INVOICE_EXTS = {"csv": "purchase_csv", "xlsx": "purchase_xlsx"}


class ImportJobResponse(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    filename: str
    gstin_profile_id: uuid.UUID
    period: Optional[str]
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    summary: dict[str, Any]
    error_message: Optional[str]


def _serialize(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        kind=job.kind,
        status=job.status,
        filename=job.filename,
        gstin_profile_id=job.gstin_profile_id,
        period=job.period,
        total_rows=job.total_rows,
        accepted_rows=job.accepted_rows,
        rejected_rows=job.rejected_rows,
        duplicate_rows=job.duplicate_rows,
        summary=job.summary,
        error_message=job.error_message,
    )


def _write_upload(job_id: uuid.UUID, data: bytes) -> None:
    os.makedirs(settings.upload_dir, exist_ok=True)
    path = os.path.join(settings.upload_dir, str(job_id))
    with open(path, "wb") as f:
        f.write(data)


def _extension(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] or "").lower()


# ---------------------------------------------------------------------------
# POST /imports/invoices  (purchase or sales register)
# ---------------------------------------------------------------------------


@router.post(
    "/invoices",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_invoices(
    gstin_profile_id: uuid.UUID = Form(...),
    direction: Literal["purchase", "sale"] = Form(...),
    file: UploadFile = File(...),
    user: AppUser = Depends(get_current_user),
    _legal: None = Depends(require_legal_accepted),
) -> ImportJobResponse:
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_INVOICE_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported extension .{ext}; expected csv or xlsx",
        )
    kind_prefix = "sales" if direction == "sale" else "purchase"
    kind = f"{kind_prefix}_{ext}"

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")

    # Manage the session lifecycle explicitly so we can commit the
    # import_job row BEFORE enqueuing — otherwise a synchronous test
    # queue (or a very fast real worker) would race the transaction and
    # see no row via ``_load_job``.
    with firm_scoped_session(user.firm_id) as session:
        job = ImportJob(
            firm_id=user.firm_id,
            gstin_profile_id=gstin_profile_id,
            uploaded_by=user.id,
            kind=kind,
            filename=file.filename or f"upload.{ext}",
        )
        session.add(job)
        session.flush()
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="import.enqueued",
            entity_type="import_job",
            entity_id=job.id,
            metadata={
                "kind": kind,
                "filename": job.filename,
                "gstin_profile_id": str(gstin_profile_id),
            },
        )
        # Materialize before session close
        _ = (job.id, job.kind, job.status, job.summary, job.gstin_profile_id,
             job.period, job.total_rows, job.accepted_rows,
             job.rejected_rows, job.duplicate_rows, job.error_message)

    _write_upload(job.id, data)

    q = get_queue()
    q.enqueue(job_functions.run_invoice_import, str(job.id))

    # If sync-mode ran the job, re-fetch the row so the response shows
    # the completed status/counts. In async mode we return the queued state.
    if not settings.queue_async:
        job = _refresh_job(user.firm_id, job.id)

    return _serialize(job)


# ---------------------------------------------------------------------------
# POST /imports/gstr2b
# ---------------------------------------------------------------------------


@router.post(
    "/gstr2b",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_gstr2b(
    gstin_profile_id: uuid.UUID = Form(...),
    period: str = Form(..., pattern=r"^[0-9]{6}$"),
    file: UploadFile = File(...),
    user: AppUser = Depends(get_current_user),
    _legal: None = Depends(require_legal_accepted),
) -> ImportJobResponse:
    ext = _extension(file.filename or "")
    if ext != "json":
        raise HTTPException(
            status_code=415, detail=f"unsupported extension .{ext}; expected json"
        )
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")

    with firm_scoped_session(user.firm_id) as session:
        job = ImportJob(
            firm_id=user.firm_id,
            gstin_profile_id=gstin_profile_id,
            uploaded_by=user.id,
            kind="gstr2b_json",
            filename=file.filename or "gstr2b.json",
            period=period,
        )
        session.add(job)
        session.flush()
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="import.enqueued",
            entity_type="import_job",
            entity_id=job.id,
            metadata={
                "kind": "gstr2b_json",
                "period": period,
                "filename": job.filename,
                "gstin_profile_id": str(gstin_profile_id),
            },
        )
        _ = (job.id, job.kind, job.status, job.summary, job.gstin_profile_id,
             job.period, job.total_rows, job.accepted_rows,
             job.rejected_rows, job.duplicate_rows, job.error_message)

    _write_upload(job.id, data)

    q = get_queue()
    q.enqueue(job_functions.run_gstr2b_import, str(job.id))

    if not settings.queue_async:
        job = _refresh_job(user.firm_id, job.id)

    return _serialize(job)


def _refresh_job(firm_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
    """Read the freshly-updated row back through a firm-scoped session."""
    with firm_scoped_session(firm_id) as session:
        j = session.get(ImportJob, job_id)
        if j is None:
            raise HTTPException(status_code=500, detail="job vanished")
        _ = (j.id, j.kind, j.status, j.filename, j.gstin_profile_id, j.period,
             j.total_rows, j.accepted_rows, j.rejected_rows, j.duplicate_rows,
             j.summary, j.error_message)
        return j


# ---------------------------------------------------------------------------
# GET /imports/{id} + list
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=ImportJobResponse)
def get_import_job(
    job_id: uuid.UUID,
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ImportJobResponse:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import job not found")
    _ = (
        job.id, job.kind, job.status, job.filename, job.gstin_profile_id,
        job.period, job.total_rows, job.accepted_rows, job.rejected_rows,
        job.duplicate_rows, job.summary, job.error_message,
    )
    return _serialize(job)


@router.get("", response_model=list[ImportJobResponse])
def list_imports(
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[ImportJobResponse]:
    rows = (
        session.execute(
            select(ImportJob).order_by(ImportJob.uploaded_at.desc()).limit(200)
        )
        .scalars()
        .all()
    )
    out = []
    for job in rows:
        _ = (
            job.id, job.kind, job.status, job.filename, job.gstin_profile_id,
            job.period, job.total_rows, job.accepted_rows, job.rejected_rows,
            job.duplicate_rows, job.summary, job.error_message,
        )
        out.append(_serialize(job))
    return out


# ---------------------------------------------------------------------------
# GET /imports/unified — UNIONs import_job (uploads) + gsp_pull_attempt
# (live pulls) in one list, labeled by source. Powers the imports page's
# "everything in one place, labeled" view (P2 stage 4 requirement).
# ---------------------------------------------------------------------------


@router.get("/unified/list")
def list_imports_unified(
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[dict]:
    from sqlalchemy import text as _text

    rows = session.execute(
        _text(
            """
            SELECT
                'upload'::text AS source_kind,
                id::text,
                kind::text AS label,
                status::text AS status,
                filename,
                period,
                uploaded_at AS at,
                accepted_rows,
                rejected_rows,
                duplicate_rows,
                error_message,
                NULL::text AS error_kind
            FROM import_job
            UNION ALL
            SELECT
                'gsp_api'::text AS source_kind,
                id::text,
                'gstr2b_gsp_pull'::text AS label,
                status::text AS status,
                NULL::text AS filename,
                period,
                started_at AS at,
                0 AS accepted_rows,
                0 AS rejected_rows,
                0 AS duplicate_rows,
                error_message,
                error_kind
            FROM gsp_pull_attempt
            ORDER BY at DESC
            LIMIT 200
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /imports/{id}/errors.csv — materialize rejects for download
# ---------------------------------------------------------------------------


@router.get("/{job_id}/errors.csv")
def download_errors(
    job_id: uuid.UUID,
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> Response:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import job not found")
    csv_bytes = rejects_to_csv(job.rejected_rows_json or [])
    filename = f"import-{job_id}-errors.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
