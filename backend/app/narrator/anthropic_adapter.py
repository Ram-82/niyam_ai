"""Anthropic Claude adapter for the narrator.

Design choices worth flagging:

* **Prompt caching on the system prompt.** The system prompt (which
  enumerates the honesty rule + output shape) never changes across
  requests. Tagging it with ``cache_control={"type": "ephemeral"}``
  lets Anthropic reuse the KV cache — small cost win at demo scale,
  meaningful cost win once we drive many CAs through the same shell.
* **Structured output.** Response format is a strict JSON object with
  four string keys — the four prose blocks. That way the validator can
  operate per-block and the caller does not have to parse prose to
  find block boundaries.
* **Model + config from settings.** No hardcoded model — Stage tests
  can drop in Haiku, prod runs Opus, and either can be swapped without
  code changes.
* **Never retry inside the adapter.** The service layer decides retry
  policy (currently: one retry with a stricter reminder on
  ``NumberHallucination``); the adapter is idempotent per call.

Requires ``anthropic>=0.40`` — added to pyproject in this stage.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.narrator.types import (
    Language,
    LANGUAGE_LABELS,
    NarrationFacts,
    NarrationOutput,
    NarratorError,
    TokenUsage,
)


log = logging.getLogger("niyam.narrator.anthropic")


# System prompt is a constant so it caches cleanly. Any change here
# invalidates the prompt cache — treat it like a code change, not a
# config knob.
_SYSTEM_PROMPT = """\
You are the narration layer inside a GST compliance product for Indian
Chartered Accountants. Your only job is to turn a frozen sheet of facts
(computed by deterministic engines upstream) into short, plain-language
prose that will be reviewed by the CA before it reaches the client.

RULES YOU MUST NOT BREAK:

1. Every rupee figure, count, percentage, or year in your output must
   appear verbatim in the FACTS block below. Do not round. Do not
   average. Do not compute a percentage. Do not write "roughly ₹43,000"
   when the fact is ₹43,000 — write ₹43,000. If a number is not in the
   facts, do not include it.
2. You are not a tax advisor. Do not offer opinions on whether a filing
   is compliant, or predict what the GSTN will do, or recommend supplier
   chases. State what happened; the CA decides what to do.
3. The client's language for this run is stated in LANGUAGE. If it is
   English, use natural business-register English (Indian usage
   welcome — "lakh", "crore"). If it is one of hi/kn/mr, produce prose
   in that language using the same numeric forms present in FACTS.
4. Output MUST be a single JSON object with exactly these string keys:
   {"page1_health", "page1_tax_position", "page2_attention",
    "page2_ask_your_ca"}
   Do not add other keys. Do not wrap in prose. Empty string is a valid
   value for page2_ask_your_ca when there is nothing specific to raise.

Prose targets:
* page1_health: 2–3 sentences. Sales, purchases, margin for the period.
* page1_tax_position: 1–2 sentences. Tax paid vs due, readiness score,
  and days-to-due.
* page2_attention: bulleted-list-shaped prose enumerating the top
  blockers. Include owner ("your CA" for owner=ca, "you" for
  owner=client). Never generic advice.
* page2_ask_your_ca: one line the client can raise with their CA, drawn
  from the facts. Empty string if nothing specific bubbles up.
"""


_STRICTER_REMINDER = (
    "\n\nAn earlier attempt at this run emitted a number NOT in the "
    "facts sheet. That is a hard failure. Re-read the FACTS block and "
    "use ONLY those numeric values. Do not round to the nearest "
    "thousand, do not compute percentages, do not merge two values."
)


def _facts_prompt(facts: NarrationFacts, language: Language) -> str:
    """Render the facts sheet as a plain-text block the model can quote.

    Money is presented as ₹-prefixed rupee amounts (whole rupees), which
    is the form the validator accepts. Presenting paise here would let
    the model re-normalise and drift.
    """

    def r(paise: int) -> str:
        # Whole-rupee Indian-grouped, matching mock_adapter._rupees but
        # without importing (mock_adapter is a separate adapter, we do
        # not want a runtime import chain).
        p = abs(paise)
        rupees = (p + 50) // 100
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
        sign = "-" if paise < 0 else ""
        return f"₹{sign}{grouped}"

    lines = [
        f"LANGUAGE: {LANGUAGE_LABELS.get(language, language)} ({language})",
        f"CLIENT: {facts.client_name}",
        f"CA FIRM: {facts.firm_name}",
        f"PERIOD: {facts.period}",
        f"RETURN TYPE: {facts.return_type}",
        f"READINESS SCORE: {facts.readiness_score}",
        f"DAYS TO DUE: {facts.days_to_due}",
        "",
        f"SALES: {r(facts.sales_paise)}",
        f"PURCHASES: {r(facts.purchases_paise)}",
        f"MARGIN: {r(facts.margin_paise)}",
        "",
        f"TAX PAID: {r(facts.tax_paid_paise)}",
        f"TAX DUE: {r(facts.tax_due_paise)}",
        "",
        f"ITC — matched: {r(facts.itc_matched_paise)}",
        f"ITC — probable: {r(facts.itc_probable_paise)}",
        f"ITC — supplier_default: {r(facts.itc_supplier_default_paise)} "
        f"({facts.itc_supplier_default_count} suppliers)",
        f"ITC — missing register entries: {r(facts.itc_missing_entry_paise)}",
        "",
        "TOP BLOCKERS (owner in parens):",
    ]
    if facts.top_blockers:
        for b in facts.top_blockers:
            lines.append(
                f"  - {b.description} [{r(b.paise_impact)}] ({b.owner})"
            )
    else:
        lines.append("  (none)")
    return "\n".join(lines)


class AnthropicNarrator:
    """Anthropic Claude adapter.

    Uses the messages API with structured JSON output. Does NOT retry
    internally — the service decides retry policy.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 800,
    ) -> None:
        try:
            import anthropic  # local import so P1 dev without the SDK still boots
        except ImportError as e:
            raise NarratorError(
                "anthropic SDK not installed. Add anthropic>=0.40 to pyproject."
            ) from e
        if not api_key:
            raise NarratorError("ANTHROPIC_API_KEY not set for AnthropicNarrator")
        self.provider = "anthropic"
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._max_tokens = max_tokens

    def narrate(
        self,
        facts: NarrationFacts,
        language: Language,
        *,
        strict_reminder: bool = False,
    ) -> NarrationOutput:
        system_blocks = [
            {
                "type": "text",
                "text": _SYSTEM_PROMPT + (_STRICTER_REMINDER if strict_reminder else ""),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        user_text = (
            _facts_prompt(facts, language)
            + "\n\nReply with a single JSON object; nothing before or after it."
        )
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user_text}],
        )
        # Content is a list of blocks; concatenate any text blocks.
        raw = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "")
        raw = raw.strip()
        # Trim optional ```json ... ``` fencing if the model added it.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise NarratorError(
                f"anthropic returned non-JSON body (first 200 chars): {raw[:200]!r}"
            ) from e
        # Extract cost meter fields from msg.usage. The SDK exposes
        # these as attributes on a pydantic model; use getattr so the
        # code doesn't crash if a future SDK version renames a field.
        usage = getattr(msg, "usage", None)
        return NarrationOutput(
            page1_health=str(payload.get("page1_health", "")).strip(),
            page1_tax_position=str(payload.get("page1_tax_position", "")).strip(),
            page2_attention=str(payload.get("page2_attention", "")).strip(),
            page2_ask_your_ca=str(payload.get("page2_ask_your_ca", "")).strip(),
            provider=self.provider,
            model=self.model,
            language=language,
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                cache_read_input_tokens=getattr(
                    usage, "cache_read_input_tokens", None
                ),
                cache_creation_input_tokens=getattr(
                    usage, "cache_creation_input_tokens", None
                ),
            ),
        )
