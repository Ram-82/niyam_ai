"""Narrator orchestration + retry policy + audit trail.

Entry points:

* :func:`get_adapter` — returns a :class:`Narrator` per ``settings.narrator_mode``.
* :func:`narrate_for_period` — the full flow that the API calls:
    facts_builder → adapter.narrate → validator → (retry once on
    hallucination) → persist to narration_run → return NarrationOutput.

Retry policy: on a first-attempt ``NumberHallucination``, we retry once
against the same adapter with a stricter reminder appended to the
system prompt. A second hallucination bails loudly — the CA sees a
"narration failed, generate again" surface, never mock prose passed off
as machine output.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.auth import audit
from app.config import settings
from app.db import firm_scoped_session
from app.narrator import validator
from app.narrator.facts_builder import FactsUnavailable, build_facts
from app.narrator.mock_adapter import MockNarrator
from app.narrator.types import (
    Language,
    Narrator,
    NarratorDisabled,
    NarratorError,
    NarrationFacts,
    NarrationOutput,
    NumberHallucination,
)


log = logging.getLogger("niyam.narrator.service")


def get_adapter() -> Narrator:
    """Return the adapter for ``settings.narrator_mode``.

    Raises :class:`NarratorDisabled` when the feature flag is off, so
    callers can render "narration is not enabled for this environment"
    without leaking which adapter would have run.
    """
    if not settings.narrator_enabled:
        raise NarratorDisabled(
            "narrator disabled (set NARRATOR_ENABLED=1 to enable)"
        )
    if settings.narrator_mode == "mock":
        return MockNarrator()
    if settings.narrator_mode == "anthropic":
        # Local import so a mock-mode deployment does not need the SDK.
        from app.narrator.anthropic_adapter import AnthropicNarrator

        return AnthropicNarrator(
            api_key=settings.anthropic_api_key,
            model=settings.narrator_model,
        )
    raise NarratorError(
        f"unknown NARRATOR_MODE={settings.narrator_mode!r} (expected mock|anthropic)"
    )


def _to_blocks(out: NarrationOutput) -> dict[str, str]:
    return {
        "page1_health": out.page1_health,
        "page1_tax_position": out.page1_tax_position,
        "page2_attention": out.page2_attention,
        "page2_ask_your_ca": out.page2_ask_your_ca,
    }


def _call_adapter(
    adapter: Narrator,
    facts: NarrationFacts,
    language: Language,
    *,
    strict: bool,
) -> NarrationOutput:
    """Adapters vary in whether they accept ``strict_reminder``. We
    call through in a way that supports both."""
    call = getattr(adapter, "narrate")
    try:
        return call(facts, language, strict_reminder=strict)  # type: ignore[call-arg]
    except TypeError:
        # Mock adapter has the simple signature.
        return call(facts, language)


def _facts_to_dict(facts: NarrationFacts) -> dict:
    """JSON-safe dict for audit persistence."""
    return {
        "period": facts.period,
        "return_type": facts.return_type,
        "firm_name": facts.firm_name,
        "client_name": facts.client_name,
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
            "supplier_default_count": facts.itc_supplier_default_count,
        },
        "readiness_score": facts.readiness_score,
        "days_to_due": facts.days_to_due,
        "top_blockers": [
            {
                "kind": b.kind,
                "owner": b.owner,
                "description": b.description,
                "paise_impact": b.paise_impact,
            }
            for b in facts.top_blockers
        ],
        "rule_pack_version": facts.rule_pack_version,
    }


def _persist_run(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    return_type: str,
    period: str,
    language: str,
    facts: NarrationFacts,
    output: NarrationOutput,
    generated_by: Optional[str | uuid.UUID],
) -> uuid.UUID:
    """Insert one narration_run row + one audit_log row.

    The table is APPEND ONLY (see migration 0009); a CA edit of the
    prose happens on a separate ``narration_edit`` row (not built here
    yet) referring back by narration_run_id.
    """
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                INSERT INTO narration_run (
                    firm_id, gstin_profile_id, return_type, period,
                    language, provider, model,
                    facts, output, generated_by
                ) VALUES (
                    :fid, :gpid, :rt, :p,
                    :lang, :prov, :model,
                    CAST(:facts AS JSONB), CAST(:output AS JSONB), :gb
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "rt": return_type,
                "p": period,
                "lang": language,
                "prov": output.provider,
                "model": output.model,
                "facts": json.dumps(_facts_to_dict(facts)),
                "output": json.dumps(
                    {
                        "page1_health": output.page1_health,
                        "page1_tax_position": output.page1_tax_position,
                        "page2_attention": output.page2_attention,
                        "page2_ask_your_ca": output.page2_ask_your_ca,
                    }
                ),
                "gb": str(generated_by) if generated_by else None,
            },
        )
        run_id = row.scalar_one()
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=generated_by,
            action="narration.generated",
            entity_type="gstin_profile",
            entity_id=gstin_profile_id,
            metadata={
                "narration_run_id": str(run_id),
                "period": period,
                "return_type": return_type,
                "language": language,
                "provider": output.provider,
                "model": output.model,
            },
        )
    return run_id


def narrate_for_period(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    return_type: str,
    period: str,
    language: Language,
    user_id: Optional[str | uuid.UUID] = None,
) -> tuple[NarrationOutput, uuid.UUID]:
    """Full flow. Returns the narration + the persisted narration_run id.

    Raises:
      NarratorDisabled — feature flag off.
      FactsUnavailable — no readiness_snapshot for the triple.
      NumberHallucination — model emitted a bad number twice in a row.
    """
    adapter = get_adapter()  # may raise NarratorDisabled
    with firm_scoped_session(firm_id) as db:
        facts = build_facts(
            db,
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            return_type=return_type,
            period=period,
        )

    # First attempt.
    output = _call_adapter(adapter, facts, language, strict=False)
    try:
        validator.validate_output_blocks(facts=facts, blocks=_to_blocks(output))
    except NumberHallucination as first_err:
        log.warning(
            "narrator.hallucination attempt=1 provider=%s offending=%s",
            output.provider,
            first_err.offending,
        )
        # Retry once with a stricter reminder.
        output = _call_adapter(adapter, facts, language, strict=True)
        try:
            validator.validate_output_blocks(
                facts=facts, blocks=_to_blocks(output)
            )
        except NumberHallucination as second_err:
            log.error(
                "narrator.hallucination attempt=2 provider=%s offending=%s",
                output.provider,
                second_err.offending,
            )
            raise

    run_id = _persist_run(
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        return_type=return_type,
        period=period,
        language=language,
        facts=facts,
        output=output,
        generated_by=user_id,
    )
    return output, run_id
