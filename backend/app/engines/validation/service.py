"""DB-integrated validation runner.

* Loads invoices for a (gstin_profile_id, period) into ``CanonicalInvoice``
  form so the pipeline can chew on them.
* Precomputes ``duplicate_key_counts`` for R007 by grouping in Python
  (fine for P1 volumes — a firm has O(1000) invoices per GSTIN per period).
* Calls ``run_pipeline`` for each invoice.
* Replaces existing UNRESOLVED flags for the same (invoice_id,
  rule_pack_version) — resolved flags stay for history.

Idempotency: re-running against the same period + rule_pack_version
does not double the flag rows.
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import firm_scoped_session
from app.engines.validation.gstin import state_code as gstin_state_code
from app.engines.validation.pipeline import run_pipeline
from app.engines.validation.types import Flag, ValidationContext
from app.ingestion.canonical import CanonicalInvoice, normalize_invoice_number
from app.rules.pack import get_active_rule_pack


@dataclass
class ValidationRunSummary:
    invoices_evaluated: int
    flags_written: int
    by_rule: dict[str, int]
    rule_pack_version: str


def validate_period(
    firm_id: uuid.UUID | str,
    gstin_profile_id: uuid.UUID | str,
    period: str,
    today: Optional[date] = None,
    annual_turnover_paise: Optional[int] = None,
) -> ValidationRunSummary:
    """Run all P1 rules over every invoice matching (gstin_profile_id,
    invoice_date's YYYYMM == period). Persist flags. Return a summary."""
    pack = get_active_rule_pack()
    tz = ZoneInfo(settings.display_tz)
    _today = today or datetime.now(tz=tz).date()

    with firm_scoped_session(firm_id) as session:
        client_state = _lookup_client_state_code(session, gstin_profile_id)
        rows = _load_invoices_for_period(session, gstin_profile_id, period)

    invoices = [_row_to_canonical(r) for r in rows]
    dupe_counts = _compute_duplicate_counts(invoices)

    ctx = ValidationContext(
        rule_pack_version=pack.version,
        rule_pack_payload=pack.payload,
        period=period,
        today=_today,
        client_state_code=client_state,
        annual_turnover_paise=annual_turnover_paise,
        duplicate_key_counts=dupe_counts,
    )

    per_invoice_flags: dict[uuid.UUID, list[Flag]] = {}
    by_rule: Counter = Counter()
    for row, inv in zip(rows, invoices):
        flags = run_pipeline(inv, ctx)
        if flags:
            per_invoice_flags[row["id"]] = flags
            for f in flags:
                by_rule[f.rule_code] += 1

    total_written = _persist_flags(
        firm_id=firm_id,
        rule_pack_version=pack.version,
        per_invoice_flags=per_invoice_flags,
    )

    return ValidationRunSummary(
        invoices_evaluated=len(invoices),
        flags_written=total_written,
        by_rule=dict(by_rule),
        rule_pack_version=pack.version,
    )


# ---------------------------------------------------------------------------
# DB helpers — all called inside a firm_scoped_session
# ---------------------------------------------------------------------------


def _lookup_client_state_code(session: Session, gstin_profile_id) -> str:
    row = session.execute(
        text("SELECT gstin, state_code FROM gstin_profile WHERE id = :id"),
        {"id": str(gstin_profile_id)},
    ).mappings().first()
    if row is None:
        raise LookupError(f"gstin_profile {gstin_profile_id} not found")
    # Prefer the explicit column; fall back to the first 2 chars of the GSTIN.
    return row["state_code"] or gstin_state_code(row["gstin"])


def _load_invoices_for_period(
    session: Session, gstin_profile_id, period: str
) -> list[dict]:
    year = int(period[:4])
    month = int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT id, gstin_profile_id, direction, invoice_number,
                   invoice_date, counterparty_gstin, taxable_value_paise,
                   cgst_paise, sgst_paise, igst_paise, total_paise, hsn_sac
            FROM invoice
            WHERE gstin_profile_id = :gid
              AND EXTRACT(YEAR FROM invoice_date) = :year
              AND EXTRACT(MONTH FROM invoice_date) = :month
              AND status = 'active'
            """
        ),
        {"gid": str(gstin_profile_id), "year": year, "month": month},
    ).mappings().all()
    return [dict(r) for r in rows]


def _row_to_canonical(row: dict) -> CanonicalInvoice:
    return CanonicalInvoice(
        gstin_profile_id=str(row["gstin_profile_id"]),
        direction=row["direction"],
        invoice_number=row["invoice_number"],
        invoice_date=row["invoice_date"],
        counterparty_gstin=row["counterparty_gstin"],
        taxable_value_paise=row["taxable_value_paise"],
        cgst_paise=row["cgst_paise"],
        sgst_paise=row["sgst_paise"],
        igst_paise=row["igst_paise"],
        total_paise=row["total_paise"],
        hsn_sac=row["hsn_sac"],
    )


def _compute_duplicate_counts(
    invoices: list[CanonicalInvoice],
) -> dict[tuple[str, str], int]:
    counts: Counter = Counter()
    for inv in invoices:
        if not inv.counterparty_gstin:
            continue
        counts[(
            inv.counterparty_gstin.upper(),
            normalize_invoice_number(inv.invoice_number),
        )] += 1
    return dict(counts)


def _persist_flags(
    firm_id: uuid.UUID | str,
    rule_pack_version: str,
    per_invoice_flags: dict[uuid.UUID, list[Flag]],
) -> int:
    """Replace UNRESOLVED flags for the given rule_pack_version per invoice.

    Resolved flags stay put (history). Idempotency: running twice with
    the same inputs leaves the same rows.
    """
    if not per_invoice_flags:
        return 0
    total = 0
    with firm_scoped_session(firm_id) as session:
        for invoice_id, flags in per_invoice_flags.items():
            session.execute(
                text(
                    "DELETE FROM validation_flag "
                    "WHERE invoice_id = :id "
                    "  AND rule_pack_version = :v "
                    "  AND resolved = FALSE"
                ),
                {"id": str(invoice_id), "v": rule_pack_version},
            )
            for f in flags:
                session.execute(
                    text(
                        """
                        INSERT INTO validation_flag (
                            firm_id, invoice_id, rule_code,
                            rule_pack_version, severity, message
                        ) VALUES (
                            :firm_id, :inv, :rc,
                            :v, :sev, :msg
                        )
                        """
                    ),
                    {
                        "firm_id": str(firm_id),
                        "inv": str(invoice_id),
                        "rc": f.rule_code,
                        "v": rule_pack_version,
                        "sev": f.severity,
                        "msg": f.message,
                    },
                )
                total += 1
    return total
