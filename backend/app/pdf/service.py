"""Assemble a NarrationRun → PDF bytes.

Loads the persisted narration_run (facts + output blocks) plus the firm
name for the letterhead, re-runs the paise-honesty validator against
the persisted prose blocks (defensive — if a bug or a manual DB edit
mutated an approved narration to include a bad number, the render
refuses rather than shipping bad prose to the client), and hands off
to :mod:`app.pdf.renderer`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db import firm_scoped_session
from app.narrator import validator
from app.narrator.types import BlockerFact, NarrationFacts, NumberHallucination
from app.pdf.renderer import render_template_to_pdf


log = logging.getLogger("niyam.pdf.service")


_MONTH_LABELS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _period_label(period: str) -> str:
    if len(period) != 6 or not period.isdigit():
        return period
    year, month = int(period[:4]), int(period[4:])
    if not 1 <= month <= 12:
        return period
    return f"{_MONTH_LABELS[month - 1]} {year}"


def _facts_from_persisted(facts_json: dict) -> NarrationFacts:
    """Reconstruct a NarrationFacts from the JSONB that was persisted at
    narration time. We need this to feed the validator, which operates
    on the dataclass shape."""
    itc = facts_json.get("itc") or {}
    return NarrationFacts(
        period=facts_json.get("period", ""),
        return_type=facts_json.get("return_type", "GSTR1"),
        firm_name=facts_json.get("firm_name", ""),
        client_name=facts_json.get("client_name", ""),
        sales_paise=int(facts_json.get("sales_paise") or 0),
        purchases_paise=int(facts_json.get("purchases_paise") or 0),
        margin_paise=int(facts_json.get("margin_paise") or 0),
        tax_paid_paise=int(facts_json.get("tax_paid_paise") or 0),
        tax_due_paise=int(facts_json.get("tax_due_paise") or 0),
        itc_matched_paise=int(itc.get("matched_paise") or 0),
        itc_probable_paise=int(itc.get("probable_paise") or 0),
        itc_supplier_default_paise=int(itc.get("supplier_default_paise") or 0),
        itc_missing_entry_paise=int(itc.get("missing_entry_paise") or 0),
        itc_supplier_default_count=int(itc.get("supplier_default_count") or 0),
        readiness_score=int(facts_json.get("readiness_score") or 0),
        days_to_due=int(facts_json.get("days_to_due") or 0),
        top_blockers=tuple(
            BlockerFact(
                kind=b.get("kind", ""),
                owner=b.get("owner", "ca"),
                description=b.get("description", ""),
                paise_impact=int(b.get("paise_impact") or 0),
            )
            for b in (facts_json.get("top_blockers") or [])
        ),
        rule_pack_version=facts_json.get("rule_pack_version", ""),
    )


class NarrationRunUnavailable(RuntimeError):
    """The narration_run does not exist under the caller's firm."""


def render_narration_pdf(
    *,
    firm_id: str | uuid.UUID,
    narration_run_id: str | uuid.UUID,
) -> bytes:
    """Load a persisted narration_run and render it to PDF bytes.

    Raises:
      NarrationRunUnavailable — no row for this id under caller's firm.
      NumberHallucination — the persisted prose contains a number not
        in the persisted facts sheet. This should never happen — the
        writer path validates before insert — but the check is here as
        defence-in-depth against manual DB edits or an unreviewed prose
        override.
    """
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                SELECT
                    nr.language, nr.provider, nr.model,
                    nr.return_type::text AS return_type, nr.period,
                    nr.facts, nr.output, nr.generated_at,
                    cf.name AS firm_name
                FROM narration_run nr
                JOIN ca_firm cf ON cf.id = nr.firm_id
                WHERE nr.id = :id
                """
            ),
            {"id": str(narration_run_id)},
        ).mappings().first()
    if row is None:
        raise NarrationRunUnavailable(str(narration_run_id))

    facts_json = row["facts"] or {}
    output_json = row["output"] or {}
    facts = _facts_from_persisted(facts_json)

    # Defence-in-depth honesty check. The narrator service already ran
    # this before persisting; running it again at render time catches
    # any post-facto mutation (a manual UPDATE that shouldn't have
    # happened, a corrupt migration, etc.) before bad prose reaches
    # the CA-approved delivery.
    validator.validate_output_blocks(
        facts=facts,
        blocks={
            "page1_health": output_json.get("page1_health", ""),
            "page1_tax_position": output_json.get("page1_tax_position", ""),
            "page2_attention": output_json.get("page2_attention", ""),
            "page2_ask_your_ca": output_json.get("page2_ask_your_ca", ""),
        },
    )

    generated_at: datetime = row["generated_at"]
    context = {
        "firm_name": row["firm_name"] or "",
        "client_name": facts_json.get("client_name") or "",
        "period_label": _period_label(row["period"]),
        "return_type": row["return_type"],
        "language": row["language"],
        "narration": {
            "page1_health": output_json.get("page1_health", ""),
            "page1_tax_position": output_json.get("page1_tax_position", ""),
            "page2_attention": output_json.get("page2_attention", ""),
            "page2_ask_your_ca": output_json.get("page2_ask_your_ca", ""),
        },
        "facts": {
            "sales_paise": facts.sales_paise,
            "purchases_paise": facts.purchases_paise,
            "margin_paise": facts.margin_paise,
            "tax_paid_paise": facts.tax_paid_paise,
            "tax_due_paise": facts.tax_due_paise,
            "itc": {
                "matched_paise": facts.itc_matched_paise,
                "probable_paise": facts.itc_probable_paise,
                "supplier_default_paise": facts.itc_supplier_default_paise,
                "missing_entry_paise": facts.itc_missing_entry_paise,
            },
            "readiness_score": facts.readiness_score,
            "days_to_due": facts.days_to_due,
            "rule_pack_version": facts.rule_pack_version,
        },
        "generated_at": generated_at.strftime("%d %b %Y %H:%M UTC"),
    }
    return render_template_to_pdf("two_pager.html", context)
