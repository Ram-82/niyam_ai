"""LLM vernacular-narration stub — shim to :mod:`app.narrator`.

The stub used to hard-raise so P1 could never accidentally ship
placeholder prose. Now the real narrator lives in ``app/narrator/`` and
this module is a compatibility layer:

* Callers that already imported ``narrate(facts, language)`` here still
  work when the feature flag is on.
* When ``settings.narrator_enabled`` is False (the default), the shim
  raises the same :class:`LLMUnavailable` a P1 caller would have seen
  from the original stub — so leaving the flag off remains equivalent
  to "P1 stubbed" behaviour.

Prefer importing from ``app.narrator`` directly in new code.
"""
from __future__ import annotations

from typing import Any

from app.narrator import service as _narrator_service
from app.narrator.types import (
    NarratorDisabled,
    NarrationFacts,
    NumberHallucination,
)


class LLMUnavailable(RuntimeError):
    """Kept for import compatibility — raised when the narrator is disabled."""


def narrate(facts: dict[str, Any], language: str) -> dict[str, str]:
    """Legacy shim. Prefer ``app.narrator.service.narrate_for_period``.

    Accepts the P1-style dict + language and delegates to the current
    adapter. Raises :class:`LLMUnavailable` when the feature flag is
    off (matches the original stub contract).
    """
    try:
        adapter = _narrator_service.get_adapter()
    except NarratorDisabled as e:
        raise LLMUnavailable(str(e)) from e

    # The dict interface predates NarrationFacts; require a facts dict
    # with the same keys and hand back the four prose blocks.
    facts_obj = NarrationFacts(
        period=facts.get("period", ""),
        return_type=facts.get("return_type", "GSTR1"),
        firm_name=facts.get("firm_name", ""),
        client_name=facts.get("client_name", ""),
        sales_paise=int(facts.get("sales_paise", 0)),
        purchases_paise=int(facts.get("purchases_paise", 0)),
        margin_paise=int(facts.get("margin_paise", 0)),
        tax_paid_paise=int(facts.get("tax_paid_paise", 0)),
        tax_due_paise=int(facts.get("tax_due_paise", 0)),
        itc_matched_paise=int(facts.get("itc_matched_paise", 0)),
        itc_probable_paise=int(facts.get("itc_probable_paise", 0)),
        itc_supplier_default_paise=int(facts.get("itc_supplier_default_paise", 0)),
        itc_missing_entry_paise=int(facts.get("itc_missing_entry_paise", 0)),
        itc_supplier_default_count=int(facts.get("itc_supplier_default_count", 0)),
        readiness_score=int(facts.get("readiness_score", 0)),
        days_to_due=int(facts.get("days_to_due", 0)),
    )
    out = adapter.narrate(facts_obj, language)  # type: ignore[arg-type]
    from app.narrator import validator

    validator.validate_output_blocks(
        facts=facts_obj,
        blocks={
            "page1_health": out.page1_health,
            "page1_tax_position": out.page1_tax_position,
            "page2_attention": out.page2_attention,
            "page2_ask_your_ca": out.page2_ask_your_ca,
        },
    )
    return {
        "page1_health": out.page1_health,
        "page1_tax_position": out.page1_tax_position,
        "page2_attention": out.page2_attention,
        "page2_ask_your_ca": out.page2_ask_your_ca,
    }
