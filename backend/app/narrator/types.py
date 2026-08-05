"""Data contracts + Protocol for the narrator adapters.

The frozen ``NarrationFacts`` dict is the *only* number-bearing input
allowed to reach the LLM. The ``narrate`` Protocol return
(``NarrationOutput``) is what the CA reviews and edits before delivery.

Why frozen dataclasses (``frozen=True``) — the facts represent a
point-in-time snapshot of the deterministic-engine outputs. Once the
narrator has them, no code path should mutate them; a follow-on regen
must build a fresh facts object from a fresh snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


Language = Literal["en", "hi", "kn", "mr"]
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "mr": "Marathi",
}


@dataclass(frozen=True)
class BlockerFact:
    kind: str
    owner: Literal["ca", "client"]
    description: str
    paise_impact: int


@dataclass(frozen=True)
class NarrationFacts:
    """Frozen snapshot passed to the narrator. All money is paise.

    The narrator NEVER receives derived numbers it might be tempted to
    recompute — pre-derive here (in ``facts_builder``) so the LLM has a
    complete, verbatim-copyable sheet.
    """

    period: str  # YYYYMM
    return_type: Literal["GSTR1", "GSTR3B"]
    firm_name: str
    client_name: str

    # P&L context for the "how the business did" block.
    sales_paise: int
    purchases_paise: int
    margin_paise: int

    # Tax position for the "what you owe / what you paid" block.
    tax_paid_paise: int
    tax_due_paise: int

    # ITC bucket totals — mirror the reconciliation summary but flattened
    # so the narrator does not walk nested keys.
    itc_matched_paise: int
    itc_probable_paise: int
    itc_supplier_default_paise: int
    itc_missing_entry_paise: int
    itc_supplier_default_count: int  # "N suppliers"

    # Readiness posture.
    readiness_score: int  # 0-100
    days_to_due: int  # negative if past due

    # The top action items, already sorted by paise_impact DESC upstream.
    top_blockers: tuple[BlockerFact, ...] = field(default_factory=tuple)

    # Rule pack that produced these numbers. Threaded through so the
    # narration can be re-generated deterministically against the same
    # inputs even after a rule-pack bump.
    rule_pack_version: str = ""


@dataclass(frozen=True)
class NarrationOutput:
    """The four prose blocks the template engine slots into the 2-pager.

    ``page1_health`` — 2-3 sentences on P&L for the period.
    ``page1_tax_position`` — 1-2 sentences on tax paid vs due + readiness posture.
    ``page2_attention`` — bulleted-list-shaped prose enumerating the top
        blockers with owner ("you" / "your CA"). Never generic advice.
    ``page2_ask_your_ca`` — one line the client is invited to raise with
        their CA. Empty string when nothing specific bubbles up.

    ``provider`` + ``model`` + ``language`` are attribution metadata
    stored alongside the narration in ``narration_run`` so a later CA
    edit can see what the machine originally said.
    """

    page1_health: str
    page1_tax_position: str
    page2_attention: str
    page2_ask_your_ca: str
    provider: str
    model: str
    language: str


class NarratorError(RuntimeError):
    """Base class for narrator failures."""


class NarratorDisabled(NarratorError):
    """Feature flag off. Callers should treat like the old stub."""


class NumberHallucination(NarratorError):
    """The output contained a number not present in the frozen facts.

    This is the load-bearing safety check. If it fires the caller
    should NOT surface the output to the CA; instead log + retry (once)
    with a stronger reminder in the prompt, then bail loudly if it
    fires again. See :func:`app.narrator.service.narrate_for_period`.
    """

    def __init__(self, offending: list[str], allowed_sample: list[str]) -> None:
        super().__init__(
            f"Narrator emitted disallowed numbers: {offending!r}. "
            f"Allowed sample: {allowed_sample!r}"
        )
        self.offending = offending
        self.allowed_sample = allowed_sample


class Narrator(Protocol):
    """Adapter interface. See ``mock_adapter`` and ``anthropic_adapter``
    for the two shipped implementations."""

    provider: str
    model: str

    def narrate(self, facts: NarrationFacts, language: Language) -> NarrationOutput:  # pragma: no cover
        ...
