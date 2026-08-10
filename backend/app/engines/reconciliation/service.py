"""DB integration for reconciliation.

``reconcile_period(firm_id, gstin_profile_id, period)``:

1. Creates a ``reconciliation_run`` row (status=running, pinned to the
   latest ``gstn_pull`` for the period and to the active rule pack).
2. Loads register invoices for the period and b2b entries from the
   latest 2B pull.
3. Runs the three-pass ``passes.reconcile``.
4. Bulk-inserts ``match_result`` rows for pairs + residuals.
5. Updates the run: status=completed, finished_at, summary JSONB.

No 2B pull for the period → the run is created with a NULL-like sentinel
gstn_pull_id? No — the schema requires NOT NULL. We raise instead and
the caller (worker or API) surfaces the error.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import firm_scoped_session
from app.engines.reconciliation.passes import reconcile
from app.engines.reconciliation.types import (
    B2BLine,
    ReconConfig,
    ReconResult,
    RegisterLine,
)
from app.ingestion.canonical import normalize_invoice_number
from app.rules.pack import get_active_rule_pack


class NoTwoBPullError(RuntimeError):
    """No GSTR-2B pull exists for the (gstin_profile_id, period)."""


@dataclass
class ReconRunResult:
    run_id: uuid.UUID
    summary: dict[str, Any]
    rule_pack_version: str


def reconcile_period(
    firm_id: uuid.UUID | str,
    gstin_profile_id: uuid.UUID | str,
    period: str,
) -> ReconRunResult:
    pack = get_active_rule_pack()
    cfg = _cfg_from_pack(pack.payload)

    with firm_scoped_session(firm_id) as session:
        pull_id = _latest_gstn_pull(session, gstin_profile_id, period)
        if pull_id is None:
            raise NoTwoBPullError(
                f"no GSTR2B pull for gstin_profile_id={gstin_profile_id} "
                f"period={period}"
            )
        register = _load_register(session, gstin_profile_id, period)
        b2b = _load_b2b(session, pull_id)
        run_id = _create_run(
            session,
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            period=period,
            pull_id=pull_id,
            rule_pack_version=pack.version,
        )

    result = reconcile(register, b2b, cfg)

    with firm_scoped_session(firm_id) as session:
        cdn_count, cdn_paise = _load_cdn_stats(session, pull_id)
        result.cdn_count = cdn_count
        result.cdn_paise = cdn_paise
        _persist_pairs_and_residuals(
            session,
            firm_id=firm_id,
            run_id=run_id,
            result=result,
            rule_pack_version=pack.version,
        )
        summary = result.summary()
        _finish_run(session, run_id=run_id, summary=summary)

    return ReconRunResult(
        run_id=run_id, summary=summary, rule_pack_version=pack.version
    )


# ---------------------------------------------------------------------------
# Config extraction
# ---------------------------------------------------------------------------


def _cfg_from_pack(payload: dict) -> ReconConfig:
    r = payload.get("reconciliation", {})
    return ReconConfig(
        exact_amount_tolerance_paise=int(r.get("exact_amount_tolerance_paise", 100)),
        date_window_days=int(r.get("date_window_days", 5)),
        amount_tolerance_percent=float(r.get("amount_tolerance_percent", 1.0)),
        probable_confidence_threshold=float(
            r.get("probable_confidence_threshold", 0.70)
        ),
        fuzzy_score_weights=dict(
            r.get(
                "fuzzy_score_weights",
                {"number_similarity": 0.5, "date_closeness": 0.25, "amount_closeness": 0.25},
            )
        ),
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _latest_gstn_pull(
    session: Session, gstin_profile_id, period: str
) -> uuid.UUID | None:
    row = session.execute(
        text(
            "SELECT id FROM gstn_pull "
            "WHERE gstin_profile_id = :gid "
            "  AND return_type = 'GSTR2B' "
            "  AND period = :p "
            "ORDER BY pulled_at DESC LIMIT 1"
        ),
        {"gid": str(gstin_profile_id), "p": period},
    ).scalar()
    return row


def _load_register(
    session: Session, gstin_profile_id, period: str
) -> list[RegisterLine]:
    year, month = int(period[:4]), int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT id, counterparty_gstin, invoice_number, invoice_date,
                   total_paise
            FROM invoice
            WHERE gstin_profile_id = :gid
              AND direction = 'purchase'
              AND status = 'active'
              AND counterparty_gstin IS NOT NULL
              AND EXTRACT(YEAR FROM invoice_date) = :y
              AND EXTRACT(MONTH FROM invoice_date) = :m
            """
        ),
        {"gid": str(gstin_profile_id), "y": year, "m": month},
    ).mappings().all()
    return [
        RegisterLine(
            invoice_id=r["id"],
            supplier_gstin=r["counterparty_gstin"].upper(),
            invoice_number=r["invoice_number"],
            normalized_number=normalize_invoice_number(r["invoice_number"]),
            invoice_date=r["invoice_date"],
            total_paise=int(r["total_paise"]),
        )
        for r in rows
    ]


def _load_b2b(session: Session, gstn_pull_id) -> list[B2BLine]:
    rows = session.execute(
        text(
            """
            SELECT id, supplier_gstin, invoice_number, invoice_date,
                   taxable_value_paise, tax_paise_breakdown, itc_available
            FROM b2b_entry
            WHERE gstn_pull_id = :pid
              AND note_type IS NULL  -- P1 skips CDN entries
            """
        ),
        {"pid": str(gstn_pull_id)},
    ).mappings().all()
    lines: list[B2BLine] = []
    for r in rows:
        tb = r["tax_paise_breakdown"] or {}
        total = (
            int(r["taxable_value_paise"])
            + int(tb.get("cgst", 0))
            + int(tb.get("sgst", 0))
            + int(tb.get("igst", 0))
            + int(tb.get("cess", 0))
        )
        lines.append(
            B2BLine(
                b2b_entry_id=r["id"],
                supplier_gstin=r["supplier_gstin"].upper(),
                invoice_number=r["invoice_number"],
                normalized_number=normalize_invoice_number(r["invoice_number"]),
                invoice_date=r["invoice_date"],
                total_paise=total,
                itc_available=bool(r["itc_available"]),
            )
        )
    return lines


def _load_cdn_stats(session: Session, gstn_pull_id) -> tuple[int, int]:
    """Return (count, total_paise) for CDN entries in this pull."""
    row = session.execute(
        text(
            """
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(taxable_value_paise
                       + (tax_paise_breakdown->>'cgst')::bigint
                       + (tax_paise_breakdown->>'sgst')::bigint
                       + (tax_paise_breakdown->>'igst')::bigint
                       + (tax_paise_breakdown->>'cess')::bigint), 0) AS paise
            FROM b2b_entry
            WHERE gstn_pull_id = :pid
              AND note_type IS NOT NULL
            """
        ),
        {"pid": str(gstn_pull_id)},
    ).mappings().one()
    return int(row["cnt"]), int(row["paise"])


def _create_run(
    session: Session,
    *,
    firm_id,
    gstin_profile_id,
    period: str,
    pull_id,
    rule_pack_version: str,
) -> uuid.UUID:
    row = session.execute(
        text(
            """
            INSERT INTO reconciliation_run (
                firm_id, gstin_profile_id, period, status,
                rule_pack_version, gstn_pull_id, started_at
            ) VALUES (
                :fid, :gid, :p, 'running',
                :v, :pid, now()
            )
            RETURNING id
            """
        ),
        {
            "fid": str(firm_id),
            "gid": str(gstin_profile_id),
            "p": period,
            "v": rule_pack_version,
            "pid": str(pull_id),
        },
    )
    return row.scalar_one()


def _persist_pairs_and_residuals(
    session: Session,
    *,
    firm_id,
    run_id,
    result: ReconResult,
    rule_pack_version: str,
) -> None:
    for pair in result.pairs:
        session.execute(
            text(
                """
                INSERT INTO match_result (
                    firm_id, run_id, invoice_id, b2b_entry_id,
                    bucket, confidence, rule_pack_version
                ) VALUES (
                    :fid, :rid, :iid, :bid,
                    CAST(:bucket AS match_bucket), :conf, :v
                )
                """
            ),
            {
                "fid": str(firm_id),
                "rid": str(run_id),
                "iid": str(pair.invoice_id),
                "bid": str(pair.b2b_entry_id),
                "bucket": pair.bucket,
                "conf": float(pair.confidence),
                "v": rule_pack_version,
            },
        )
    for res in result.residuals:
        context = _residual_context(res)
        session.execute(
            text(
                """
                INSERT INTO match_result (
                    firm_id, run_id, invoice_id, b2b_entry_id,
                    bucket, confidence, rule_pack_version, context
                ) VALUES (
                    :fid, :rid, :iid, :bid,
                    CAST(:bucket AS match_bucket), 0.0, :v,
                    CAST(:ctx AS JSONB)
                )
                """
            ),
            {
                "fid": str(firm_id),
                "rid": str(run_id),
                "iid": str(res.invoice_id) if res.invoice_id else None,
                "bid": str(res.b2b_entry_id) if res.b2b_entry_id else None,
                "bucket": res.bucket,
                "v": rule_pack_version,
                "ctx": json.dumps(context),
            },
        )


def _residual_context(res) -> dict:  # noqa: ANN001
    """Serialize NearMiss list for a supplier_default residual. Other
    buckets get {} — the column still exists for future annotations."""
    if res.bucket != "supplier_default" or not res.near_misses:
        return {}
    return {
        "near_misses": [
            {
                "b2b_entry_id": str(nm.b2b_entry_id),
                "supplier_gstin": nm.supplier_gstin,
                "invoice_number": nm.invoice_number,
                "invoice_date": nm.invoice_date.isoformat(),
                "total_paise": nm.total_paise,
                "similarity": nm.similarity,
            }
            for nm in res.near_misses
        ],
    }


def _finish_run(session: Session, *, run_id, summary: dict) -> None:
    session.execute(
        text(
            "UPDATE reconciliation_run SET "
            "status='completed', finished_at=now(), summary=CAST(:s AS JSONB) "
            "WHERE id=:id"
        ),
        {"id": str(run_id), "s": json.dumps(summary)},
    )
