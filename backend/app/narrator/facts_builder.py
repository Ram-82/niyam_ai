"""Assemble ``NarrationFacts`` from the deterministic engines' outputs.

The narrator must never call these queries itself — it receives a
frozen sheet. Any regen against the same (gstin_profile, period,
return_type) triple should produce the same facts unless a subsequent
engine run wrote a new ``readiness_snapshot`` or ``reconciliation_run``.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.narrator.types import BlockerFact, NarrationFacts


class FactsUnavailable(RuntimeError):
    """No readiness_snapshot yet for the requested (gstin, period, return_type)."""


def _due_date(return_type: str, period: str, pack_payload: dict) -> Optional[date]:
    """Compute the due date for the period using rule-pack settings.

    Only implements the monthly cadence for P1. QRMP / non-standard
    schemes fall back to None and the narrator will not mention days.
    """
    if len(period) != 6 or not period.isdigit():
        return None
    y, m = int(period[:4]), int(period[4:])
    # Due dates: filing month is m+1 for GSTR1/3B in monthly cadence.
    if m == 12:
        fy, fm = y + 1, 1
    else:
        fy, fm = y, m + 1
    stat = (pack_payload or {}).get("statutory") or {}
    due = stat.get("due_dates") or {}
    if return_type == "GSTR1":
        day = int(due.get("gstr1_monthly", 11))
    elif return_type == "GSTR3B":
        day = int(due.get("gstr3b_monthly", 20))
    else:
        return None
    try:
        return date(fy, fm, day)
    except ValueError:
        return None


def build_facts(
    session: OrmSession,
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    return_type: str,
    period: str,
    today: Optional[date] = None,
) -> NarrationFacts:
    """Pull the latest engine outputs and package them for the narrator.

    Raises :class:`FactsUnavailable` if no ``readiness_snapshot`` exists
    for the triple — the CA is expected to run the readiness engine
    before requesting narration.
    """
    from app.rules.pack import get_active_rule_pack

    pack = get_active_rule_pack()
    pack_payload = pack.payload if pack else {}

    # Firm + client display names.
    firm_row = session.execute(
        text("SELECT name FROM ca_firm WHERE id = :id"),
        {"id": str(firm_id)},
    ).first()
    firm_name = (firm_row[0] if firm_row else "") or ""

    client_row = session.execute(
        text(
            """
            SELECT c.trade_name, gp.gstin
            FROM gstin_profile gp
            JOIN client c ON c.id = gp.client_id
            WHERE gp.id = :gpid
            """
        ),
        {"gpid": str(gstin_profile_id)},
    ).first()
    client_name = (client_row[0] if client_row else "") or ""

    # Latest readiness snapshot — this is the entry point. If none exists
    # the caller must run the scoring engine first.
    rs = session.execute(
        text(
            """
            SELECT score, blockers, arithmetic, rule_pack_version, computed_at
            FROM readiness_snapshot
            WHERE gstin_profile_id = :g
              AND return_type = :rt
              AND period = :p
            ORDER BY computed_at DESC
            LIMIT 1
            """
        ),
        {"g": str(gstin_profile_id), "rt": return_type, "p": period},
    ).mappings().first()
    if rs is None:
        raise FactsUnavailable(
            f"No readiness snapshot for gstin={gstin_profile_id} "
            f"return_type={return_type} period={period}."
        )
    arithmetic = rs["arithmetic"] or {}
    blockers = rs["blockers"] or []

    # Reconciliation summary — the ITC bucket paise + supplier_default count.
    recon = session.execute(
        text(
            """
            SELECT summary
            FROM reconciliation_run
            WHERE gstin_profile_id = :g AND period = :p
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"g": str(gstin_profile_id), "p": period},
    ).first()
    recon_summary = (recon[0] if recon else None) or {}
    matched = recon_summary.get("matched", {})
    probable = recon_summary.get("probable", {})
    sup_def = recon_summary.get("supplier_default", {})
    missing = recon_summary.get("missing_entry", {})

    # Sales + purchases for the period (paise). Direction is stored on
    # invoice; this is the same slice the scoring engine uses.
    y, m = int(period[:4]), int(period[4:])
    sales_paise = int(
        session.execute(
            text(
                "SELECT COALESCE(SUM(total_paise), 0) FROM invoice "
                "WHERE gstin_profile_id = :g AND direction = 'sale' "
                "  AND status = 'active' "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {"g": str(gstin_profile_id), "y": y, "m": m},
        ).scalar()
        or 0
    )
    purchases_paise = int(
        session.execute(
            text(
                "SELECT COALESCE(SUM(total_paise), 0) FROM invoice "
                "WHERE gstin_profile_id = :g AND direction = 'purchase' "
                "  AND status = 'active' "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {"g": str(gstin_profile_id), "y": y, "m": m},
        ).scalar()
        or 0
    )
    margin_paise = sales_paise - purchases_paise

    # Tax figures — arithmetic breakdown carries them if the scoring
    # engine computed them; otherwise fall back to zeros so the narrator
    # doesn't invent numbers.
    tax_paid_paise = int(arithmetic.get("tax_paid_paise") or 0)
    tax_due_paise = int(arithmetic.get("tax_due_paise") or 0)

    # Days-to-due — positive if in the future, negative if overdue.
    today = today or date.today()
    due = _due_date(return_type, period, pack_payload)
    days_to_due = (due - today).days if due else 0

    top_blockers = tuple(
        BlockerFact(
            kind=b.get("kind", ""),
            owner=b.get("owner", "ca") if b.get("owner") in ("ca", "client") else "ca",
            description=b.get("description", ""),
            paise_impact=int(b.get("paise_impact") or 0),
        )
        for b in sorted(
            blockers, key=lambda x: int(x.get("paise_impact") or 0), reverse=True
        )[:5]
    )

    return NarrationFacts(
        period=period,
        return_type=return_type,  # type: ignore[arg-type]
        firm_name=firm_name,
        client_name=client_name,
        sales_paise=sales_paise,
        purchases_paise=purchases_paise,
        margin_paise=margin_paise,
        tax_paid_paise=tax_paid_paise,
        tax_due_paise=tax_due_paise,
        itc_matched_paise=int(matched.get("paise") or 0),
        itc_probable_paise=int(probable.get("paise") or 0),
        itc_supplier_default_paise=int(sup_def.get("paise") or 0),
        itc_missing_entry_paise=int(missing.get("paise") or 0),
        itc_supplier_default_count=int(sup_def.get("count") or 0),
        readiness_score=int(rs["score"] or 0),
        days_to_due=days_to_due,
        top_blockers=top_blockers,
        rule_pack_version=rs["rule_pack_version"] or "",
    )
