"""Deterministic template-based narrator for dev + tests.

Produces prose only from values already in ``facts`` — so the validator
should NEVER fire on this adapter. If it does, that is a validator bug,
not an adapter bug, and the test suite should catch it before the
Anthropic adapter is even wired.

Non-English languages are shipped as stub prefixes for now (``[hi] ...``
etc.) — the intended P3 shape is to render the same facts through
localised templates, not to translate the English strings. When we
add real translations, the assertion "every emitted number appears in
facts" still holds because the same numeric slots are filled.
"""
from __future__ import annotations

from app.narrator.types import Language, NarrationFacts, NarrationOutput


PROVIDER = "mock"
MODEL = "template-v1"


def _rupees(paise: int) -> str:
    """Format a paise integer as ₹N,NN,NNN (Indian grouping, whole rupees)."""
    if paise == 0:
        return "₹0"
    negative = paise < 0
    p = abs(paise)
    rupees = (p + 50) // 100  # rounded to nearest whole rupee
    s = str(rupees)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.append(rest[-2:])
            rest = rest[:-2]
        parts.append(rest)
        grouped = ",".join(reversed(parts)) + "," + last3
    sign = "-" if negative else ""
    return f"₹{sign}{grouped}"


def _render_en(facts: NarrationFacts) -> tuple[str, str, str, str]:
    period_label = _period_label(facts.period)

    page1_health = (
        f"For {period_label}, sales came in at {_rupees(facts.sales_paise)} "
        f"and purchases at {_rupees(facts.purchases_paise)}, leaving a "
        f"margin of {_rupees(facts.margin_paise)}."
    )

    if facts.days_to_due >= 0:
        due_line = (
            f"You have {facts.days_to_due} days to the {facts.return_type} due date."
        )
    else:
        due_line = (
            f"The {facts.return_type} due date is {abs(facts.days_to_due)} days past."
        )
    page1_tax_position = (
        f"Tax paid so far this period is {_rupees(facts.tax_paid_paise)}; "
        f"tax due is {_rupees(facts.tax_due_paise)}. "
        f"Filing readiness stands at {facts.readiness_score} out of 100. "
        f"{due_line}"
    )

    if facts.top_blockers:
        bullets = []
        for b in facts.top_blockers[:3]:
            owner_label = "your CA" if b.owner == "ca" else "you"
            bullets.append(
                f"• {b.description} — {_rupees(b.paise_impact)}, {owner_label} to act."
            )
        page2_attention = (
            "The items below need attention before filing:\n" + "\n".join(bullets)
        )
    else:
        page2_attention = "No action items outstanding for this period."

    if facts.itc_supplier_default_count > 0:
        page2_ask_your_ca = (
            f"Ask your CA about the {facts.itc_supplier_default_count} suppliers "
            f"whose ITC is at risk ({_rupees(facts.itc_supplier_default_paise)} total)."
        )
    else:
        page2_ask_your_ca = ""

    return page1_health, page1_tax_position, page2_attention, page2_ask_your_ca


def _period_label(period: str) -> str:
    """YYYYMM → 'July 2026'. Falls back to the raw period on malformed input."""
    if len(period) != 6 or not period.isdigit():
        return period
    year = period[:4]
    month = int(period[4:])
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    if not 1 <= month <= 12:
        return period
    return f"{months[month - 1]} {year}"


class MockNarrator:
    """Template renderer. Same interface as :class:`AnthropicNarrator`."""

    provider = PROVIDER
    model = MODEL

    def narrate(
        self, facts: NarrationFacts, language: Language
    ) -> NarrationOutput:
        blocks = _render_en(facts)
        if language == "en":
            page1_health, page1_tax_position, page2_attention, page2_ask_your_ca = blocks
        else:
            # Stub non-English: prefix with tag so it is visibly not-a-real-translation
            # in the UI. Real translations land in P3 with the Anthropic adapter.
            tag = f"[{language}] "
            page1_health = tag + blocks[0]
            page1_tax_position = tag + blocks[1]
            page2_attention = tag + blocks[2]
            page2_ask_your_ca = tag + blocks[3] if blocks[3] else ""
        return NarrationOutput(
            page1_health=page1_health,
            page1_tax_position=page1_tax_position,
            page2_attention=page2_attention,
            page2_ask_your_ca=page2_ask_your_ca,
            provider=self.provider,
            model=self.model,
            language=language,
        )
