"""Google Gemini adapter for the narrator.

Same Protocol as :class:`AnthropicNarrator`, different provider. Ships
alongside Anthropic so a firm can pick per-need:

* Anthropic (Claude) — best vernacular quality in our informal testing,
  SOC 2, US region.
* Gemini — free tier available (with caveat: free-tier prompts may be
  used for model improvement per Google's terms), Vertex AI paid tier
  offers India-region routing, DPA + SOC 2 on paid.
* Mock — no external call at all; template output.

See ``docs/narrator-security.md`` for the CA-facing decision matrix.

Design differences vs :class:`AnthropicNarrator`:

* Gemini's Python SDK does NOT do prompt caching automatically the way
  Anthropic's ``cache_control={"type":"ephemeral"}`` header does — you
  have to explicitly create a ``CachedContent`` object and reference it
  by id on each call. **This adapter does NOT wire that up yet** —
  Gemini's fresh-input pricing is low enough (Flash: $0.35/M input)
  that the pilot volume doesn't justify the extra plumbing. Add
  explicit caching in a P3 followup if the observability dashboard
  shows Gemini becoming a material cost line.
* Gemini's JSON mode uses ``response_mime_type='application/json'``
  in the generation config rather than a header. We rely on that
  instead of stripping markdown fences from the response body.

Requires ``google-generativeai>=0.8`` in pyproject.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.narrator.anthropic_adapter import (
    _facts_prompt,
    _STRICTER_REMINDER,
    _SYSTEM_PROMPT,
)
from app.narrator.types import (
    Language,
    NarrationFacts,
    NarrationOutput,
    NarratorError,
    TokenUsage,
)


log = logging.getLogger("niyam.narrator.gemini")


class GeminiNarrator:
    """Google Gemini adapter.

    Uses the ``google.generativeai`` SDK with JSON-mode structured
    output. Does NOT retry internally — the service decides retry
    policy (currently: one retry with a stricter reminder on
    ``NumberHallucination``).

    Args:
        api_key: Gemini API key (register at aistudio.google.com).
        model: model id — e.g. ``gemini-2.5-flash`` (recommended for
            cost) or ``gemini-2.5-pro`` (higher quality vernacular).
        max_tokens: output token limit. Default 800 mirrors the
            Anthropic adapter — the narration blocks are short.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 800,
    ) -> None:
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise NarratorError(
                "google-generativeai SDK not installed. "
                "Add google-generativeai>=0.8 to pyproject."
            ) from e
        if not api_key:
            raise NarratorError("GEMINI_API_KEY not set for GeminiNarrator")
        self.provider = "gemini"
        self.model = model
        self._genai = genai
        self._api_key = api_key
        self._max_tokens = max_tokens
        genai.configure(api_key=api_key)

    def narrate(
        self,
        facts: NarrationFacts,
        language: Language,
        *,
        strict_reminder: bool = False,
    ) -> NarrationOutput:
        system_text = _SYSTEM_PROMPT + (_STRICTER_REMINDER if strict_reminder else "")
        user_text = (
            _facts_prompt(facts, language)
            + "\n\nReply with a single JSON object; nothing before or after it."
        )

        # Gemini's GenerativeModel is thin — construct fresh per call
        # since the system instruction may vary (strict_reminder path).
        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_text,
        )
        generation_config = {
            "max_output_tokens": self._max_tokens,
            # JSON mode — Gemini guarantees valid JSON in .text without
            # markdown fencing. Cheaper than a schema; the narrator's
            # 4-key shape is validated by the caller.
            "response_mime_type": "application/json",
        }
        response = model.generate_content(
            user_text,
            generation_config=generation_config,
        )

        raw = getattr(response, "text", "") or ""
        raw = raw.strip()
        # Defensive: JSON-mode responses should not have fences, but
        # some model versions do add them anyway. Strip if present.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise NarratorError(
                f"gemini returned non-JSON body (first 200 chars): {raw[:200]!r}"
            ) from e

        # Extract usage from Gemini's response.usage_metadata.
        # Attribute names per google-generativeai SDK docs:
        #   prompt_token_count            → fresh input tokens
        #   candidates_token_count        → output tokens
        #   cached_content_token_count    → cache-hit tokens (if using
        #                                    explicit CachedContent — not
        #                                    wired yet, will be 0)
        #   total_token_count             → sum
        usage = getattr(response, "usage_metadata", None)
        return NarrationOutput(
            page1_health=str(payload.get("page1_health", "")).strip(),
            page1_tax_position=str(payload.get("page1_tax_position", "")).strip(),
            page2_attention=str(payload.get("page2_attention", "")).strip(),
            page2_ask_your_ca=str(payload.get("page2_ask_your_ca", "")).strip(),
            provider=self.provider,
            model=self.model,
            language=language,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
                cache_read_input_tokens=getattr(
                    usage, "cached_content_token_count", None
                ),
                # Gemini doesn't expose a separate "cache creation" count;
                # cache creation happens at CachedContent creation time,
                # not per-call. Leave as None to distinguish from
                # "measured 0".
                cache_creation_input_tokens=None,
            ),
        )
