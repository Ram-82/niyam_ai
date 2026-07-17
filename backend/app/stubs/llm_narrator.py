"""LLM vernacular-narration interface — P2.

**Intended contract.** In P2, ``narrate(facts, language)`` accepts a
frozen ``facts`` dict (P&L, tax due, ITC bucket totals, top blockers —
all integers in paise, computed by the deterministic engines) and a
target ISO language code (``kn``, ``hi``, ``mr``, ``en``). It returns
short prose blocks that a template engine assembles into the MSME
2-pager. **Hard rule: the LLM never computes or invents a number.**
Every rupee figure in the output must be one the caller passed in
verbatim — the narrator is a translation/tone layer, nothing more.
Positioning depends on this: "Niyam prepares and flags; the CA
approves and advises" only holds if numeric authority stays with the
deterministic engines.

Output shape:

    {
      "page1_health": "<short prose describing sales/purchases/margin>",
      "page1_tax_position": "<prose on tax paid vs due>",
      "page2_attention": "<prose enumerating action items from `blockers`>",
      "page2_ask_your_ca": "<one-line advisory nudge or empty string>",
    }

Every block goes through the CA approval gate before delivery — the
LLM never emits directly to the client. See ``whatsapp.py`` for
delivery-side stub.

**Why stubbed in P1.** Vernacular narration + template rendering are
P3 features per the master prompt. The engines already carry the
raw facts through in JSONB (``readiness_snapshot.arithmetic``,
``reconciliation_run.summary``); when the narrator lands it consumes
those directly.
"""
from __future__ import annotations

from typing import Any


class LLMUnavailable(RuntimeError):
    """Raised so P1 callers can't accidentally ship placeholder prose."""


def narrate(facts: dict[str, Any], language: str) -> None:
    raise LLMUnavailable(
        "LLM narration is stubbed in P1. Vernacular 2-pager ships in P3."
    )
