"""Unit tests for GeminiNarrator.

Hermetic — no network. We inject a fake ``google.generativeai`` module
into ``sys.modules`` so the adapter can ``import google.generativeai
as genai`` without the real SDK. Same shape as
``test_narrator_anthropic_adapter.py``.

Load-bearing properties covered:

* Constructor rejects empty API key.
* ``genai.configure(api_key=...)`` is called with the passed key.
* ``genai.GenerativeModel(...)`` receives the system prompt via
  ``system_instruction=`` (Gemini's equivalent of Anthropic's
  ``system=`` block).
* ``generate_content`` is called with ``response_mime_type='application/json'``
  in the generation_config — this is what forces valid JSON output
  without a ```json fencing.
* ``strict_reminder=True`` appends the stricter reminder to the system
  prompt (same reminder text as AnthropicNarrator — imported from
  the shared module).
* ``response.usage_metadata`` populates ``NarrationOutput.usage``:
  ``prompt_token_count`` → ``input_tokens``,
  ``candidates_token_count`` → ``output_tokens``,
  ``cached_content_token_count`` → ``cache_read_input_tokens``.
* Malformed JSON raises ``NarratorError``.
* Missing usage_metadata → all usage fields None (defensive).
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.narrator.types import (
    BlockerFact,
    NarrationFacts,
    NarratorError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _facts(**overrides) -> NarrationFacts:
    base = dict(
        period="202607",
        return_type="GSTR1",
        firm_name="Acme CA",
        client_name="Beta Traders",
        sales_paise=1_00_00_000,
        purchases_paise=50_00_000,
        margin_paise=50_00_000,
        tax_paid_paise=25_00_000,
        tax_due_paise=30_00_000,
        itc_matched_paise=2_50_00_000,
        itc_probable_paise=1_50_00_000,
        itc_supplier_default_paise=43_00_000,
        itc_missing_entry_paise=1_20_00_000,
        itc_supplier_default_count=6,
        readiness_score=65,
        days_to_due=5,
        top_blockers=(
            BlockerFact(
                kind="supplier_default",
                owner="ca",
                description="ITC at risk from 6 suppliers",
                paise_impact=43_00_000,
            ),
        ),
        rule_pack_version="1.0.0",
    )
    base.update(overrides)
    return NarrationFacts(**base)


def _fake_response(
    body: str,
    *,
    prompt_tokens: int = 1200,
    candidate_tokens: int = 350,
    cached_tokens: int = 0,
) -> SimpleNamespace:
    """Emulate the shape returned by GenerativeModel.generate_content."""
    return SimpleNamespace(
        text=body,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=candidate_tokens,
            cached_content_token_count=cached_tokens,
        ),
    )


@pytest.fixture
def fake_genai(monkeypatch):
    """Install a fake ``google.generativeai`` module into sys.modules."""
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.generativeai")

    mock_configure = MagicMock()
    mock_generate = MagicMock()
    mock_generative_model_instance = MagicMock()
    mock_generative_model_instance.generate_content = mock_generate
    mock_generative_model_cls = MagicMock(
        return_value=mock_generative_model_instance
    )

    genai_mod.configure = mock_configure
    genai_mod.GenerativeModel = mock_generative_model_cls
    google_mod.generativeai = genai_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai_mod)

    # Expose the mocks for direct assertions.
    genai_mod._mock_configure = mock_configure
    genai_mod._mock_generate = mock_generate
    genai_mod._mock_generative_model_cls = mock_generative_model_cls
    return genai_mod


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_empty_api_key_rejected(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        with pytest.raises(NarratorError):
            GeminiNarrator(api_key="", model="gemini-2.5-flash")

    def test_provider_and_model_recorded(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        adapter = GeminiNarrator(api_key="key", model="gemini-2.5-pro")
        assert adapter.provider == "gemini"
        assert adapter.model == "gemini-2.5-pro"

    def test_sdk_configured_with_api_key(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        GeminiNarrator(api_key="test-key-xyz", model="gemini-2.5-flash")
        fake_genai._mock_configure.assert_called_once_with(api_key="test-key-xyz")


# ---------------------------------------------------------------------------
# Happy path — JSON body → NarrationOutput
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_narration_output_with_all_blocks(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        body = (
            '{"page1_health": "Sales were ₹1,00,000.", '
            '"page1_tax_position": "Tax due ₹30,000.", '
            '"page2_attention": "• Reconcile 6 suppliers.", '
            '"page2_ask_your_ca": "Confirm the treatment."}'
        )
        fake_genai._mock_generate.return_value = _fake_response(body)

        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "Sales were ₹1,00,000."
        assert out.page1_tax_position == "Tax due ₹30,000."
        assert out.page2_attention == "• Reconcile 6 suppliers."
        assert out.page2_ask_your_ca == "Confirm the treatment."
        assert out.provider == "gemini"
        assert out.model == "gemini-2.5-flash"
        assert out.language == "en"

    def test_facts_prompt_reaches_generate_content(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        adapter.narrate(_facts(), language="en")

        # First positional arg to generate_content is the user prompt.
        args, kwargs = fake_genai._mock_generate.call_args
        user_content = args[0]
        assert "SALES: ₹1,00,000" in user_content
        assert "CLIENT: Beta Traders" in user_content


# ---------------------------------------------------------------------------
# JSON mode — the load-bearing structured-output lever
# ---------------------------------------------------------------------------


class TestJsonMode:
    def test_response_mime_type_forced_to_json(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        adapter.narrate(_facts(), language="en")

        _, kwargs = fake_genai._mock_generate.call_args
        gc = kwargs["generation_config"]
        assert gc["response_mime_type"] == "application/json"
        assert gc["max_output_tokens"] == 800


# ---------------------------------------------------------------------------
# system_instruction wiring
# ---------------------------------------------------------------------------


class TestSystemInstruction:
    def test_system_prompt_passed_via_system_instruction(
        self, fake_genai
    ) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        adapter.narrate(_facts(), language="en")

        # GenerativeModel was constructed with system_instruction=<system prompt>
        _, kwargs = fake_genai._mock_generative_model_cls.call_args
        assert "system_instruction" in kwargs
        assert "verbatim in the FACTS" in kwargs["system_instruction"]

    def test_strict_true_appends_reminder(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        adapter.narrate(_facts(), language="en", strict_reminder=True)

        _, kwargs = fake_genai._mock_generative_model_cls.call_args
        assert "emitted a number NOT in the facts" in kwargs["system_instruction"]

    def test_strict_false_omits_reminder(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        adapter.narrate(_facts(), language="en", strict_reminder=False)

        _, kwargs = fake_genai._mock_generative_model_cls.call_args
        assert "emitted a number NOT in the facts" not in kwargs["system_instruction"]


# ---------------------------------------------------------------------------
# Token usage extraction
# ---------------------------------------------------------------------------


class TestTokenUsageExtraction:
    def test_usage_populated_from_usage_metadata(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}',
            prompt_tokens=1500,
            candidate_tokens=400,
            cached_tokens=1200,
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        out = adapter.narrate(_facts(), language="en")

        assert out.usage.input_tokens == 1500
        assert out.usage.output_tokens == 400
        assert out.usage.cache_read_input_tokens == 1200
        # Gemini has no separate "cache_creation" per call.
        assert out.usage.cache_creation_input_tokens is None

    def test_missing_usage_metadata_defaults_to_none(self, fake_genai) -> None:
        """Future SDK version renames the field → don't crash, log None."""
        from app.narrator.gemini_adapter import GeminiNarrator

        # Response with NO usage_metadata attribute.
        fake_genai._mock_generate.return_value = SimpleNamespace(
            text=(
                '{"page1_health":"","page1_tax_position":"",'
                '"page2_attention":"","page2_ask_your_ca":""}'
            ),
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        out = adapter.narrate(_facts(), language="en")

        assert out.usage.input_tokens is None
        assert out.usage.output_tokens is None
        assert out.usage.cache_read_input_tokens is None


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


class TestJsonParsing:
    def test_strips_json_code_fence_defensive(self, fake_genai) -> None:
        """JSON mode should not fence, but some model versions do anyway."""
        from app.narrator.gemini_adapter import GeminiNarrator

        body = (
            "```json\n"
            '{"page1_health": "OK", "page1_tax_position": "OK", '
            '"page2_attention": "OK", "page2_ask_your_ca": ""}\n'
            "```"
        )
        fake_genai._mock_generate.return_value = _fake_response(body)
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        out = adapter.narrate(_facts(), language="en")
        assert out.page1_health == "OK"

    def test_malformed_json_raises_narrator_error(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            "this is not json at all"
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        with pytest.raises(NarratorError) as exc:
            adapter.narrate(_facts(), language="en")
        assert "non-JSON" in str(exc.value) or "not json" in str(exc.value).lower()

    def test_missing_keys_default_to_empty_string(self, fake_genai) -> None:
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = _fake_response(
            '{"page1_health": "hello"}'
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "hello"
        assert out.page1_tax_position == ""
        assert out.page2_attention == ""
        assert out.page2_ask_your_ca == ""

    def test_missing_text_attribute_treated_as_empty(self, fake_genai) -> None:
        """A response with no .text attribute triggers the parse-error path."""
        from app.narrator.gemini_adapter import GeminiNarrator

        fake_genai._mock_generate.return_value = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=0,
                cached_content_token_count=0,
            ),
        )
        adapter = GeminiNarrator(api_key="k", model="gemini-2.5-flash")
        with pytest.raises(NarratorError):
            adapter.narrate(_facts(), language="en")
