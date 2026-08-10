"""Client workspace reads + workspace mutations + engine triggers.

Endpoint map:

Reads (either role, RLS-scoped):
  GET /gstins/{id}/invoices?period=YYYYMM
  GET /gstins/{id}/flags?period=YYYYMM
  GET /gstins/{id}/reconciliation?period=YYYYMM
  GET /reconciliation-runs/{id}/matches?bucket=matched|probable|supplier_default|missing_entry
  GET /gstins/{id}/readiness?return_type=GSTR1|GSTR3B&period=YYYYMM

Mutations (either role, RLS-scoped, audited):
  POST /flags/{id}/resolve
  POST /match-results/{id}/confirm
  POST /match-results/{id}/reject
  POST /match-results/{id}/mark-near-miss-reviewed
      Sets context.near_miss_reviewed_at = now() on a supplier_default
      row. The whatsapp gate checks this before allowing a supplier
      chase — step-9 acceptance criterion #2: never chase before the
      CA has reviewed the near-miss list for a plausible match.
  POST /match-results/{id}/mark-reviewed
      CA acknowledges a supplier_default or missing_entry without
      sending a chase. Sets confirmed_by/confirmed_at + context.reviewed_at.
      Optional body: { "reason": "timing gap / already recorded / etc." }.
  POST /engines/validate  {gstin_profile_id, period}
  POST /engines/reconcile {gstin_profile_id, period}
  POST /engines/score     {gstin_profile_id, return_type, period}

The trigger endpoints run the engines SYNCHRONOUSLY in P1. Fast for
P1 volumes (~1000 invoices per GSTIN per period). If profiling later
shows a bottleneck, wrap each in ``queue.enqueue`` — the engines
themselves already work outside a request context.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.auth import audit
from app.engines.reconciliation.service import (
    NoTwoBPullError,
    reconcile_period,
)
from app.engines.scoring.service import compute_and_persist
from app.engines.validation.service import validate_period
from app.models.tables import AppUser


router = APIRouter(tags=["workspace"])


# ---------------------------------------------------------------------------
# INVOICES tab
# ---------------------------------------------------------------------------


class InvoiceRow(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: str
    counterparty_gstin: Optional[str]
    total_paise: int
    hsn_sac: Optional[str]
    direction: str
    status: str
    flag_count: int


class GstinClientInfo(BaseModel):
    """Prefill data the workspace hands to DeliveryPanel so the CA does
    not have to look up the client separately + then remember to fill
    the phone into the chase modal."""
    gstin_profile_id: uuid.UUID
    gstin: str
    client_id: uuid.UUID
    trade_name: str
    language: str
    whatsapp_number: Optional[str] = None


@router.get("/gstins/{gid}/client", response_model=GstinClientInfo)
def get_gstin_client(
    gid: uuid.UUID,
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> GstinClientInfo:
    """Resolve gstin_profile → client so the workspace can prefill the
    DeliveryPanel + display the trade_name in the header without a
    second API call."""
    row = session.execute(
        text(
            """
            SELECT gp.id AS gstin_profile_id, gp.gstin,
                   c.id AS client_id, c.trade_name,
                   c.language, c.whatsapp_number
            FROM gstin_profile gp
            JOIN client c ON c.id = gp.client_id
            WHERE gp.id = :gid
            """
        ),
        {"gid": str(gid)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="gstin_profile not found")
    return GstinClientInfo(**dict(row))


@router.get("/gstins/{gid}/invoices", response_model=list[InvoiceRow])
def list_invoices(
    gid: uuid.UUID,
    period: str = Query(..., pattern=r"^[0-9]{6}$"),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[InvoiceRow]:
    y, m = int(period[:4]), int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT
                i.id, i.invoice_number, i.invoice_date, i.counterparty_gstin,
                i.total_paise, i.hsn_sac, i.direction::text, i.status::text,
                COALESCE(fc.n, 0) AS flag_count
            FROM invoice i
            LEFT JOIN (
                SELECT invoice_id, count(*) AS n
                FROM validation_flag
                WHERE resolved = FALSE
                GROUP BY invoice_id
            ) fc ON fc.invoice_id = i.id
            WHERE i.gstin_profile_id = :g
              AND EXTRACT(YEAR FROM i.invoice_date) = :y
              AND EXTRACT(MONTH FROM i.invoice_date) = :m
            ORDER BY i.invoice_date DESC, i.invoice_number
            """
        ),
        {"g": str(gid), "y": y, "m": m},
    ).mappings().all()
    return [
        InvoiceRow(
            id=r["id"],
            invoice_number=r["invoice_number"],
            invoice_date=r["invoice_date"].isoformat(),
            counterparty_gstin=r["counterparty_gstin"],
            total_paise=int(r["total_paise"]),
            hsn_sac=r["hsn_sac"],
            direction=r["direction"],
            status=r["status"],
            flag_count=int(r["flag_count"]),
        )
        for r in rows
    ]


class FlagRow(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    rule_code: str
    severity: str
    message: str
    resolved: bool
    rule_pack_version: str


@router.get("/gstins/{gid}/flags", response_model=list[FlagRow])
def list_flags(
    gid: uuid.UUID,
    period: str = Query(..., pattern=r"^[0-9]{6}$"),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[FlagRow]:
    y, m = int(period[:4]), int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT vf.id, vf.invoice_id, vf.rule_code, vf.severity::text,
                   vf.message, vf.resolved, vf.rule_pack_version
            FROM validation_flag vf
            JOIN invoice i ON i.id = vf.invoice_id
            WHERE i.gstin_profile_id = :g
              AND EXTRACT(YEAR FROM i.invoice_date) = :y
              AND EXTRACT(MONTH FROM i.invoice_date) = :m
            ORDER BY vf.severity, vf.rule_code
            """
        ),
        {"g": str(gid), "y": y, "m": m},
    ).mappings().all()
    return [FlagRow(**dict(r)) for r in rows]


class ResolveFlagRequest(BaseModel):
    resolved: bool = True
    note: Optional[str] = None


@router.post("/flags/{flag_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_flag(
    flag_id: uuid.UUID,
    payload: ResolveFlagRequest,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> dict[str, Any]:
    before = session.execute(
        text(
            "SELECT resolved, rule_code FROM validation_flag WHERE id = :id"
        ),
        {"id": str(flag_id)},
    ).mappings().first()
    if before is None:
        raise HTTPException(status_code=404, detail="flag not found")

    session.execute(
        text(
            "UPDATE validation_flag SET "
            "resolved = :r, "
            "resolved_by = :u, "
            "resolved_at = :t "
            "WHERE id = :id"
        ),
        {
            "id": str(flag_id),
            "r": payload.resolved,
            "u": str(user.id) if payload.resolved else None,
            "t": datetime.now(tz=timezone.utc) if payload.resolved else None,
        },
    )
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="flag.resolved" if payload.resolved else "flag.reopened",
        entity_type="validation_flag",
        entity_id=flag_id,
        metadata={
            "before": {"resolved": before["resolved"]},
            "after": {"resolved": payload.resolved, "note": payload.note},
            "rule_code": before["rule_code"],
        },
    )
    return {"id": str(flag_id), "resolved": payload.resolved}


# ---------------------------------------------------------------------------
# RECONCILIATION tab
# ---------------------------------------------------------------------------


class ReconSummaryResponse(BaseModel):
    run_id: Optional[uuid.UUID]
    period: str
    status: Optional[str]
    summary: dict[str, Any]
    rule_pack_version: Optional[str]
    finished_at: Optional[datetime]


@router.get("/gstins/{gid}/reconciliation", response_model=ReconSummaryResponse)
def get_reconciliation(
    gid: uuid.UUID,
    period: str = Query(..., pattern=r"^[0-9]{6}$"),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ReconSummaryResponse:
    row = session.execute(
        text(
            """
            SELECT id, period, status::text, summary, rule_pack_version,
                   finished_at
            FROM reconciliation_run
            WHERE gstin_profile_id = :g AND period = :p
            ORDER BY created_at DESC LIMIT 1
            """
        ),
        {"g": str(gid), "p": period},
    ).mappings().first()
    if row is None:
        return ReconSummaryResponse(
            run_id=None, period=period, status=None,
            summary={}, rule_pack_version=None, finished_at=None,
        )
    return ReconSummaryResponse(
        run_id=row["id"],
        period=row["period"],
        status=row["status"],
        summary=dict(row["summary"] or {}),
        rule_pack_version=row["rule_pack_version"],
        finished_at=row["finished_at"],
    )


class MatchRow(BaseModel):
    id: uuid.UUID
    bucket: str
    confidence: float
    invoice_id: Optional[uuid.UUID]
    b2b_entry_id: Optional[uuid.UUID]
    confirmed_by: Optional[uuid.UUID]
    confirmed_at: Optional[datetime]
    rejected: bool
    context: dict[str, Any]


@router.get(
    "/reconciliation-runs/{run_id}/matches",
    response_model=list[MatchRow],
)
def list_matches(
    run_id: uuid.UUID,
    bucket: Optional[str] = None,
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[MatchRow]:
    # We LEFT JOIN invoice + b2b_entry to surface supplier_gstin into
    # the row's context — the supplier-chase UI needs it for the
    # /supplier-contacts/by-gstin/{...} prefill lookup, and it is
    # cheaper to join here once than to require a per-row invoice fetch
    # from the frontend. The value is merged into context (not a
    # top-level column) so the UI's existing shape stays stable.
    sql = (
        "SELECT mr.id, mr.bucket::text AS bucket, mr.confidence, "
        "  mr.invoice_id, mr.b2b_entry_id, "
        "  mr.confirmed_by, mr.confirmed_at, mr.rejected, mr.context, "
        "  COALESCE(i.counterparty_gstin, be.supplier_gstin) AS supplier_gstin, "
        "  i.invoice_number AS register_invoice_number, "
        "  i.invoice_date AS register_invoice_date, "
        "  i.total_paise AS register_total_paise, "
        "  be.invoice_number AS b2b_invoice_number, "
        "  be.invoice_date AS b2b_invoice_date, "
        "  be.itc_available AS b2b_itc_available, "
        "  CASE WHEN be.id IS NOT NULL THEN "
        "    COALESCE(be.taxable_value_paise, 0) "
        "    + COALESCE((be.tax_paise_breakdown->>'cgst')::bigint, 0) "
        "    + COALESCE((be.tax_paise_breakdown->>'sgst')::bigint, 0) "
        "    + COALESCE((be.tax_paise_breakdown->>'igst')::bigint, 0) "
        "    + COALESCE((be.tax_paise_breakdown->>'cess')::bigint, 0) "
        "  END AS b2b_total_paise "
        "FROM match_result mr "
        "LEFT JOIN invoice i ON i.id = mr.invoice_id "
        "LEFT JOIN b2b_entry be ON be.id = mr.b2b_entry_id "
        "WHERE mr.run_id = :r"
    )
    params: dict = {"r": str(run_id)}
    if bucket:
        sql += " AND mr.bucket = CAST(:bucket AS match_bucket)"
        params["bucket"] = bucket
    sql += " ORDER BY mr.bucket, mr.confidence DESC"
    rows = session.execute(text(sql), params).mappings().all()

    def _isodate(v: Any) -> str:
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    out: list[MatchRow] = []
    for r in rows:
        ctx = dict(r["context"] or {})
        # Merge joined columns into context — never overwrite an
        # already-present key (the engine's near-miss data wins if
        # somehow set from both sides).
        if r["supplier_gstin"] and "supplier_gstin" not in ctx:
            ctx["supplier_gstin"] = r["supplier_gstin"]
        if r["register_invoice_number"] and "register_invoice_number" not in ctx:
            ctx["register_invoice_number"] = r["register_invoice_number"]
        if r["register_invoice_date"] and "register_invoice_date" not in ctx:
            ctx["register_invoice_date"] = _isodate(r["register_invoice_date"])
        if r["register_total_paise"] is not None and "register_total_paise" not in ctx:
            ctx["register_total_paise"] = int(r["register_total_paise"])
        if r["b2b_invoice_number"] and "b2b_invoice_number" not in ctx:
            ctx["b2b_invoice_number"] = r["b2b_invoice_number"]
        if r["b2b_invoice_date"] and "b2b_invoice_date" not in ctx:
            ctx["b2b_invoice_date"] = _isodate(r["b2b_invoice_date"])
        if r["b2b_total_paise"] is not None and "b2b_total_paise" not in ctx:
            ctx["b2b_total_paise"] = int(r["b2b_total_paise"])
        if r["b2b_itc_available"] is not None and "b2b_itc_available" not in ctx:
            ctx["b2b_itc_available"] = bool(r["b2b_itc_available"])
        out.append(
            MatchRow(
                id=r["id"],
                bucket=r["bucket"],
                confidence=float(r["confidence"]),
                invoice_id=r["invoice_id"],
                b2b_entry_id=r["b2b_entry_id"],
                confirmed_by=r["confirmed_by"],
                confirmed_at=r["confirmed_at"],
                rejected=r["rejected"],
                context=ctx,
            )
        )
    return out


@router.post("/match-results/{match_id}/confirm", status_code=status.HTTP_200_OK)
def confirm_match(
    match_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> dict[str, Any]:
    row = session.execute(
        text(
            "SELECT bucket::text AS bucket, confirmed_at, rejected "
            "FROM match_result WHERE id = :id"
        ),
        {"id": str(match_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row["bucket"] != "probable":
        raise HTTPException(
            status_code=400, detail=f"only probable matches can be confirmed"
        )
    # Confirm = promote to matched + stamp who + when.
    session.execute(
        text(
            "UPDATE match_result SET "
            "bucket = 'matched', confirmed_by = :u, "
            "confirmed_at = :t, rejected = FALSE "
            "WHERE id = :id"
        ),
        {
            "id": str(match_id),
            "u": str(user.id),
            "t": datetime.now(tz=timezone.utc),
        },
    )
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="match.confirmed",
        entity_type="match_result",
        entity_id=match_id,
        metadata={"before": {"bucket": "probable"}, "after": {"bucket": "matched"}},
    )
    return {"id": str(match_id), "bucket": "matched"}


@router.post("/match-results/{match_id}/reject", status_code=status.HTTP_200_OK)
def reject_match(
    match_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> dict[str, Any]:
    row = session.execute(
        text(
            "SELECT bucket::text AS bucket, confirmed_at, rejected "
            "FROM match_result WHERE id = :id"
        ),
        {"id": str(match_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row["bucket"] != "probable":
        raise HTTPException(
            status_code=400, detail="only probable matches can be rejected"
        )
    # Mark rejected — the row stays for audit. A future re-run will
    # regenerate a fresh probable if the pair still qualifies; the
    # dashboard can filter on rejected=TRUE to hide them.
    session.execute(
        text(
            "UPDATE match_result SET "
            "rejected = TRUE, confirmed_by = :u, confirmed_at = :t "
            "WHERE id = :id"
        ),
        {
            "id": str(match_id),
            "u": str(user.id),
            "t": datetime.now(tz=timezone.utc),
        },
    )
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="match.rejected",
        entity_type="match_result",
        entity_id=match_id,
        metadata={"before": {"rejected": False}, "after": {"rejected": True}},
    )
    return {"id": str(match_id), "rejected": True}


@router.post(
    "/match-results/{match_id}/mark-near-miss-reviewed",
    status_code=status.HTTP_200_OK,
)
def mark_near_miss_reviewed(
    match_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> dict[str, Any]:
    """Record that the CA reviewed the near-miss list on a supplier_default row.

    Writes ``context.near_miss_reviewed_at = now()`` while preserving all
    other keys on the context JSONB. Idempotent: calling twice overwrites
    the timestamp — no error, but every call still audits so the trail
    shows every ack.

    This endpoint is the sole way the WhatsApp supplier_chase gate
    (``app.whatsapp.gate``) becomes satisfiable — the gate looks up the
    same key on match_result.context. Do not add another writer to it.
    """
    row = session.execute(
        text(
            "SELECT bucket::text AS bucket, context "
            "FROM match_result WHERE id = :id"
        ),
        {"id": str(match_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row["bucket"] != "supplier_default":
        raise HTTPException(
            status_code=400,
            detail="near-miss review only applies to supplier_default matches",
        )
    reviewed_at = datetime.now(tz=timezone.utc)
    # jsonb_set(context, '{near_miss_reviewed_at}', to_jsonb(...)) preserves
    # other keys (near_misses[], etc.) — do NOT overwrite the whole column.
    session.execute(
        text(
            "UPDATE match_result "
            "SET context = jsonb_set("
            "    context, '{near_miss_reviewed_at}', "
            "    to_jsonb(CAST(:t AS text)), true"
            ") "
            "WHERE id = :id"
        ),
        {"id": str(match_id), "t": reviewed_at.isoformat()},
    )
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="match.near_miss_reviewed",
        entity_type="match_result",
        entity_id=match_id,
        metadata={"reviewed_at": reviewed_at.isoformat()},
    )
    return {
        "id": str(match_id),
        "near_miss_reviewed_at": reviewed_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Match override: mark-reviewed (supplier_default / missing_entry)
# ---------------------------------------------------------------------------


class MarkReviewedBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


@router.post(
    "/match-results/{match_id}/mark-reviewed",
    status_code=status.HTTP_200_OK,
)
def mark_match_reviewed(
    match_id: uuid.UUID,
    body: Optional[MarkReviewedBody] = None,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> dict[str, Any]:
    """CA acknowledges a supplier_default or missing_entry without chasing.

    Sets ``confirmed_by`` / ``confirmed_at`` to record who reviewed it and
    writes ``context.reviewed_at`` (ISO-8601) plus optional
    ``context.reviewed_reason``. Idempotent: re-calling overwrites the
    timestamp; every call audits.
    """
    row = session.execute(
        text(
            "SELECT bucket::text AS bucket, confirmed_at "
            "FROM match_result WHERE id = :id"
        ),
        {"id": str(match_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="match not found")
    if row["bucket"] not in ("supplier_default", "missing_entry"):
        raise HTTPException(
            status_code=400,
            detail="mark-reviewed only applies to supplier_default and missing_entry rows",
        )
    reviewed_at = datetime.now(tz=timezone.utc)
    import json as _json
    reason = (body.reason if body else None) or None
    patch_data: dict = {"reviewed_at": reviewed_at.isoformat()}
    if reason:
        patch_data["reviewed_reason"] = reason
    ctx_patch = _json.dumps(patch_data)
    session.execute(
        text(
            "UPDATE match_result "
            "SET confirmed_by = :u, confirmed_at = :t, "
            "    context = context || CAST(:patch AS JSONB) "
            "WHERE id = :id"
        ),
        {
            "id": str(match_id),
            "u": str(user.id),
            "t": reviewed_at,
            "patch": ctx_patch,
        },
    )
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="match.reviewed",
        entity_type="match_result",
        entity_id=match_id,
        metadata={
            "bucket": row["bucket"],
            "reviewed_at": reviewed_at.isoformat(),
            "reason": reason,
        },
    )
    return {
        "id": str(match_id),
        "reviewed_at": reviewed_at.isoformat(),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# READINESS tab
# ---------------------------------------------------------------------------


class ReadinessResponse(BaseModel):
    snapshot_id: Optional[uuid.UUID]
    return_type: str
    period: str
    score: Optional[int]
    blockers: list[dict[str, Any]]
    arithmetic: dict[str, Any]
    rule_pack_version: Optional[str]
    computed_at: Optional[datetime]


@router.get("/gstins/{gid}/readiness", response_model=ReadinessResponse)
def get_readiness(
    gid: uuid.UUID,
    return_type: str = Query(..., pattern=r"^(GSTR1|GSTR3B)$"),
    period: str = Query(..., pattern=r"^[0-9]{6}$"),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ReadinessResponse:
    row = session.execute(
        text(
            """
            SELECT id, return_type::text, period, score, blockers, arithmetic,
                   rule_pack_version, computed_at
            FROM readiness_snapshot
            WHERE gstin_profile_id = :g
              AND return_type = CAST(:rt AS return_type)
              AND period = :p
            ORDER BY computed_at DESC LIMIT 1
            """
        ),
        {"g": str(gid), "rt": return_type, "p": period},
    ).mappings().first()
    if row is None:
        return ReadinessResponse(
            snapshot_id=None,
            return_type=return_type,
            period=period,
            score=None,
            blockers=[],
            arithmetic={},
            rule_pack_version=None,
            computed_at=None,
        )
    return ReadinessResponse(
        snapshot_id=row["id"],
        return_type=row["return_type"],
        period=row["period"],
        score=int(row["score"]) if row["score"] is not None else None,
        blockers=list(row["blockers"] or []),
        arithmetic=dict(row["arithmetic"] or {}),
        rule_pack_version=row["rule_pack_version"],
        computed_at=row["computed_at"],
    )


# ---------------------------------------------------------------------------
# ENGINE TRIGGERS — sync in P1
# ---------------------------------------------------------------------------


class ValidateTriggerRequest(BaseModel):
    gstin_profile_id: uuid.UUID
    period: str = Field(pattern=r"^[0-9]{6}$")
    annual_turnover_paise: Optional[int] = None


class ReconcileTriggerRequest(BaseModel):
    gstin_profile_id: uuid.UUID
    period: str = Field(pattern=r"^[0-9]{6}$")


class ScoreTriggerRequest(BaseModel):
    gstin_profile_id: uuid.UUID
    return_type: str = Field(pattern=r"^(GSTR1|GSTR3B)$")
    period: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/engines/validate", status_code=status.HTTP_200_OK)
def trigger_validation(
    payload: ValidateTriggerRequest,
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    summary = validate_period(
        firm_id=user.firm_id,
        gstin_profile_id=payload.gstin_profile_id,
        period=payload.period,
        annual_turnover_paise=payload.annual_turnover_paise,
    )
    # audit through a fresh firm-scoped session (validate_period opens
    # its own sessions internally and commits)
    from app.db import firm_scoped_session
    with firm_scoped_session(user.firm_id) as sess:
        audit.record(
            sess,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="validation.triggered",
            entity_type="gstin_profile",
            entity_id=payload.gstin_profile_id,
            metadata={
                "period": payload.period,
                "invoices_evaluated": summary.invoices_evaluated,
                "flags_written": summary.flags_written,
                "by_rule": summary.by_rule,
            },
        )
    return {
        "invoices_evaluated": summary.invoices_evaluated,
        "flags_written": summary.flags_written,
        "by_rule": summary.by_rule,
        "rule_pack_version": summary.rule_pack_version,
    }


@router.post("/engines/reconcile", status_code=status.HTTP_200_OK)
def trigger_reconcile(
    payload: ReconcileTriggerRequest,
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        result = reconcile_period(
            firm_id=user.firm_id,
            gstin_profile_id=payload.gstin_profile_id,
            period=payload.period,
        )
    except NoTwoBPullError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from app.db import firm_scoped_session
    with firm_scoped_session(user.firm_id) as sess:
        audit.record(
            sess,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="reconciliation.triggered",
            entity_type="reconciliation_run",
            entity_id=result.run_id,
            metadata={"period": payload.period, "summary": result.summary},
        )
    return {
        "run_id": str(result.run_id),
        "summary": result.summary,
        "rule_pack_version": result.rule_pack_version,
    }


@router.post("/engines/score", status_code=status.HTTP_200_OK)
def trigger_score(
    payload: ScoreTriggerRequest,
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = compute_and_persist(
        firm_id=user.firm_id,
        gstin_profile_id=payload.gstin_profile_id,
        return_type=payload.return_type,
        period=payload.period,
    )
    from app.db import firm_scoped_session
    with firm_scoped_session(user.firm_id) as sess:
        audit.record(
            sess,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="score.triggered",
            entity_type="readiness_snapshot",
            entity_id=result.snapshot_id,
            metadata={
                "period": payload.period,
                "return_type": payload.return_type,
                "score": result.score,
                "rule_pack_version": result.rule_pack_version,
            },
        )
    return {
        "snapshot_id": str(result.snapshot_id),
        "score": result.score,
        "blockers": result.blockers,
        "arithmetic": result.arithmetic,
        "rule_pack_version": result.rule_pack_version,
    }
