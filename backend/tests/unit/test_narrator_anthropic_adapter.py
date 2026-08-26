"""Unit tests for AnthropicNarrator.

The adapter imports the ``anthropic`` SDK at construction time and
calls ``client.messages.create(...)``. We patch the SDK client via
``unittest.mock`` so these tests are hermetic — no network, no real
API key.

Load-bearing properties covered:

* Constructor rejects empty API key.
* ``system`` block is sent with ``cache_control={"type": "ephemeral"}``
  on the first text block — this is what enables prompt caching and
  drives the ~90% cache-read target after warmup.
* ``strict_reminder=True`` appends the stricter-reminder paragraph to
  the system prompt (verified by substring; exact text is a constant
  in the adapter and we don't couple to it).
* Response ``msg.usage.*`` populates ``NarrationOutput.usage`` — this
  is what the service layer writes to ``narrator_call_log`` for cost /
  cache-hit observability.
* JSON parsing tolerates ``` ```json ... ``` ``` fencing (Claude
  sometimes wraps in a code block).
* Malformed JSON raises ``NarratorError`` (never a bare exception).
* Missing keys in the JSON payload default to empty strings, not None
  (the service concatenates them into prose — None would raise).
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
    TokenUsage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _facts(**overrides) -> NarrationFacts:
    """Same fact builder used across narrator tests."""
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


def _fake_msg(
    body: str,
    *,
    input_tokens: int = 1200,
    output_tokens: int = 350,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> SimpleNamespace:
    """A fake anthropic.types.Message with .content + .usage as the SDK ships."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=body)],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
    )


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Install a fake ``anthropic`` module into sys.modules.

    The adapter does ``import anthropic`` at construction time. Injecting
    the fake keeps the real SDK out of the test path (fast + no imports
    of the real package needed).

    Returns the mock ``Anthropic`` class so a test can inspect how it
    was constructed and what ``messages.create(...)`` was called with.
    """
    fake_module = types.ModuleType("anthropic")

    mock_messages_create = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = mock_messages_create
    mock_anthropic_cls = MagicMock(return_value=mock_client_instance)
    fake_module.Anthropic = mock_anthropic_cls

    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    # Also expose the mock_messages_create for direct assertions.
    fake_module._mock_create = mock_messages_create
    fake_module._mock_client = mock_client_instance
    return fake_module


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_empty_api_key_rejected(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        with pytest.raises(NarratorError):
            AnthropicNarrator(api_key="", model="claude-opus-4-7")

    def test_provider_and_model_recorded(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        adapter = AnthropicNarrator(api_key="test-key", model="claude-sonnet-4-6")
        assert adapter.provider == "anthropic"
        assert adapter.model == "claude-sonnet-4-6"

    def test_sdk_client_constructed_with_api_key(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        AnthropicNarrator(api_key="sk-test-123", model="claude-opus-4-7")
        fake_anthropic.Anthropic.assert_called_once_with(api_key="sk-test-123")


# ---------------------------------------------------------------------------
# Happy path — JSON body → NarrationOutput
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_narration_output_with_all_blocks(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        body = (
            '{"page1_health": "Sales were ₹1,00,000.", '
            '"page1_tax_position": "Tax due ₹30,000.", '
            '"page2_attention": "• Reconcile 6 suppliers.", '
            '"page2_ask_your_ca": "Confirm the treatment."}'
        )
        fake_anthropic._mock_create.return_value = _fake_msg(body)

        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "Sales were ₹1,00,000."
        assert out.page1_tax_position == "Tax due ₹30,000."
        assert out.page2_attention == "• Reconcile 6 suppliers."
        assert out.page2_ask_your_ca == "Confirm the treatment."
        assert out.provider == "anthropic"
        assert out.model == "claude-opus-4-7"
        assert out.language == "en"

    def test_facts_prompt_reaches_messages_create(self, fake_anthropic) -> None:
        """Facts appear verbatim in the user message body."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        adapter.narrate(_facts(), language="en")

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        # Facts formatter renders 100,00,000 paise as ₹1,00,000 (Indian grouping,
        # whole rupees, rounded from paise).
        assert "SALES: ₹1,00,000" in user_content
        assert "CLIENT: Beta Traders" in user_content
        assert "PERIOD: 202607" in user_content


# ---------------------------------------------------------------------------
# Prompt caching header — the load-bearing cost lever
# ---------------------------------------------------------------------------


class TestPromptCaching:
    def test_system_block_carries_ephemeral_cache_control(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        adapter.narrate(_facts(), language="en")

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        system_blocks = kwargs["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[0]["type"] == "text"
        assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}
        # The prompt text is non-empty and mentions the honesty rule.
        assert "verbatim in the FACTS" in system_blocks[0]["text"]


# ---------------------------------------------------------------------------
# strict_reminder — retry path from service
# ---------------------------------------------------------------------------


class TestStrictReminder:
    def test_strict_true_appends_reminder(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        adapter.narrate(_facts(), language="en", strict_reminder=True)

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        sys_text = kwargs["system"][0]["text"]
        # Substring — we don't want to couple to the exact reminder wording.
        assert "emitted a number NOT in the facts" in sys_text

    def test_strict_false_omits_reminder(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        adapter.narrate(_facts(), language="en", strict_reminder=False)

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        sys_text = kwargs["system"][0]["text"]
        assert "emitted a number NOT in the facts" not in sys_text


# ---------------------------------------------------------------------------
# Token usage extraction — feeds narrator_call_log
# ---------------------------------------------------------------------------


class TestTokenUsageExtraction:
    def test_usage_populated_from_message_usage(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}',
            input_tokens=2500,
            output_tokens=420,
            cache_read=2200,
            cache_creation=300,
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.usage.input_tokens == 2500
        assert out.usage.output_tokens == 420
        assert out.usage.cache_read_input_tokens == 2200
        assert out.usage.cache_creation_input_tokens == 300

    def test_missing_usage_attribute_defaults_to_none(self, fake_anthropic) -> None:
        """If a future SDK version renames the usage field, we don't
        crash — we log NULLs and keep going."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        # Message with NO usage attribute at all.
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=(
                '{"page1_health":"","page1_tax_position":"",'
                '"page2_attention":"","page2_ask_your_ca":""}'
            ))],
        )
        fake_anthropic._mock_create.return_value = msg

        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.usage.input_tokens is None
        assert out.usage.output_tokens is None
        assert out.usage.cache_read_input_tokens is None
        assert out.usage.cache_creation_input_tokens is None


# ---------------------------------------------------------------------------
# JSON parsing edge cases
# ---------------------------------------------------------------------------


class TestJsonParsing:
    def test_strips_json_code_fence(self, fake_anthropic) -> None:
        """Claude sometimes wraps JSON in ```json ... ``` — the adapter
        strips this so the caller doesn't have to."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        body = (
            "```json\n"
            '{"page1_health": "OK", "page1_tax_position": "OK", '
            '"page2_attention": "OK", "page2_ask_your_ca": ""}\n'
            "```"
        )
        fake_anthropic._mock_create.return_value = _fake_msg(body)
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "OK"

    def test_malformed_json_raises_narrator_error(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            "this is not json at all"
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        with pytest.raises(NarratorError) as exc:
            adapter.narrate(_facts(), language="en")
        # Error message includes the offending body so operator can debug.
        assert "not json" in str(exc.value).lower() or "non-JSON" in str(exc.value)

    def test_missing_keys_default_to_empty_string(self, fake_anthropic) -> None:
        """Model returns partial JSON — we default missing blocks to ""
        so downstream string ops don't hit None."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        # Only page1_health present.
        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health": "hello"}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "hello"
        assert out.page1_tax_position == ""
        assert out.page2_attention == ""
        assert out.page2_ask_your_ca == ""

    def test_multiple_text_blocks_concatenated(self, fake_anthropic) -> None:
        """Some responses split content across multiple text blocks —
        the adapter concatenates them before parsing."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text='{"page1_health": "a", '),
                SimpleNamespace(type="text", text='"page1_tax_position": "b", '),
                SimpleNamespace(type="text", text='"page2_attention": "c", '),
                SimpleNamespace(type="text", text='"page2_ask_your_ca": "d"}'),
            ],
            usage=SimpleNamespace(
                input_tokens=100, output_tokens=50,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
            ),
        )
        fake_anthropic._mock_create.return_value = msg

        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "a"
        assert out.page2_ask_your_ca == "d"

    def test_non_text_blocks_ignored(self, fake_anthropic) -> None:
        """A response with mixed block types (thinking, tool_use, text) —
        adapter picks out just the text ones."""
        from app.narrator.anthropic_adapter import AnthropicNarrator

        msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="internal monologue"),
                SimpleNamespace(type="text", text=(
                    '{"page1_health":"real","page1_tax_position":"",'
                    '"page2_attention":"","page2_ask_your_ca":""}'
                )),
            ],
            usage=SimpleNamespace(
                input_tokens=100, output_tokens=50,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
            ),
        )
        fake_anthropic._mock_create.return_value = msg

        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        out = adapter.narrate(_facts(), language="en")

        assert out.page1_health == "real"


# ---------------------------------------------------------------------------
# max_tokens plumbed through
# ---------------------------------------------------------------------------


class TestMaxTokens:
    def test_default_max_tokens_sent(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(api_key="k", model="claude-opus-4-7")
        adapter.narrate(_facts(), language="en")

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        # Default is 800 per the adapter constructor.
        assert kwargs["max_tokens"] == 800

    def test_custom_max_tokens_respected(self, fake_anthropic) -> None:
        from app.narrator.anthropic_adapter import AnthropicNarrator

        fake_anthropic._mock_create.return_value = _fake_msg(
            '{"page1_health":"","page1_tax_position":"",'
            '"page2_attention":"","page2_ask_your_ca":""}'
        )
        adapter = AnthropicNarrator(
            api_key="k", model="claude-opus-4-7", max_tokens=1500
        )
        adapter.narrate(_facts(), language="en")

        kwargs = fake_anthropic._mock_create.call_args.kwargs
        assert kwargs["max_tokens"] == 1500
