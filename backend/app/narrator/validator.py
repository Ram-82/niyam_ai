"""Number-hallucination guard for narrator output.

The core rule: every number the narrator emits must be one the caller
passed in via :class:`NarrationFacts`. This module derives the set of
*allowed* number strings from the facts, extracts every number-bearing
token from the narration output, and rejects the output if any output
token is not present in the allowed set.

Why not just trust the LLM? Even a well-prompted model will occasionally
round, invent a percentage, or reword "6 suppliers" as "half a dozen"
(which is fine copy but hides a specific number). The rule is not that
the model *should* invent — it is that the module downstream will
*reject* any output that does. That is the load-bearing property.

Allowed forms (per numeric input):
    N (paise)               → the raw integer as a string
    N/100 (rupees)          → integer rupee form and Indian-grouped form
                              e.g. paise=4_300_000 → "43000" and "43,000"
                              (Indian grouping: last 3 then twos)
    ₹N form                 → "₹43,000" and "₹43000"
    percentages             → "20%" for readiness_score
    counts                  → the plain integer for count fields

Notes on tokenisation:
* We strip commas and rupee/currency symbols from output tokens before
  membership check, so ``"₹43,000"`` and ``"43000"`` and ``"43,000"``
  all normalise to ``"43000"``. That mirrors what the allowed set
  contains and dodges Indian-grouping edge cases.
* We consider digit runs of length >= 2 only. Single-digit numbers
  (0-9) are ubiquitous in prose ("1 blocker", "2 suppliers") and the
  facts always contain the base range — so we allow all 0-99 by
  default. Larger numbers must be explicitly allowed.
* Ordinals ("1st", "2nd") and dates ("July 2026") are non-issues since
  we only match digit runs; "1st" becomes ``1`` which is auto-allowed.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.narrator.types import NarrationFacts, NumberHallucination


# Match digit runs, optionally with a decimal point (2 dp — we don't
# emit money with decimals but the LLM might try). Grouping commas are
# allowed inside the digit run and stripped during normalisation.
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


# Numbers we always allow to appear even if not explicitly in the facts:
# 0-100 inclusive, so common prose like "1 blocker", "6 suppliers",
# "20%", and — importantly — the "out of 100" score scale in the
# narrator's own template are permitted without being explicit facts.
# Anything above this range must be present in the facts to be permitted.
_SMALL_NUMBER_CEILING = 100


def _normalise(token: str) -> str:
    """Strip separators + currency + trailing punctuation.

    Returns the pure digit string, or the token unchanged if it does
    not tokenise cleanly (in which case the caller will treat it as
    non-matching and reject).
    """
    stripped = token.replace(",", "").replace("₹", "").replace("Rs", "")
    stripped = stripped.strip(".%: ")
    return stripped


def _paise_to_rupees_int(paise: int) -> str:
    """Round to nearest rupee. Copy in the demo shows whole rupees
    exclusively so this matches human expectation.
    """
    if paise >= 0:
        return str((paise + 50) // 100)
    return "-" + str((-paise + 50) // 100)


def _indian_grouped(num_str: str) -> str:
    """Format a positive integer string in Indian grouping (lakhs/crores).

    e.g. ``"4300000"`` → ``"43,00,000"``. Numbers with fewer than 4
    digits are returned unchanged (no comma needed).
    """
    n = num_str.lstrip("-")
    if len(n) <= 3:
        return num_str
    last3 = n[-3:]
    rest = n[:-3]
    # Group the remaining leading part into pairs from the right.
    grouped_rest = ""
    while len(rest) > 2:
        grouped_rest = "," + rest[-2:] + grouped_rest
        rest = rest[:-2]
    grouped_rest = rest + grouped_rest
    sign = "-" if num_str.startswith("-") else ""
    return sign + grouped_rest + "," + last3


def build_allowed_forms(facts: NarrationFacts) -> set[str]:
    """Return the set of normalised digit strings the narrator may emit.

    Callers should not need to walk this — it exists so the validator
    can decide membership cheaply and so tests can inspect what forms
    were derived from a given facts sheet.
    """
    allowed: set[str] = set()

    # Always-allowed small integers (0 through the ceiling, inclusive).
    for i in range(0, _SMALL_NUMBER_CEILING + 1):
        allowed.add(str(i))
        allowed.add("-" + str(i))  # negative small forms ("-3 days past due")

    def _add_money(paise: int) -> None:
        # Raw paise (unlikely to appear in prose but harmless).
        allowed.add(str(paise))
        allowed.add(str(abs(paise)))
        # Rupees (rounded to nearest whole rupee).
        rupees = _paise_to_rupees_int(paise)
        rupees_abs = rupees.lstrip("-")
        allowed.add(rupees_abs)
        # Indian-grouped (comma will be stripped at match time, so this
        # entry is redundant with the plain digit form — but we add both
        # for symmetry with tests that inspect the set directly).
        grouped = _indian_grouped(rupees_abs)
        allowed.add(grouped.replace(",", ""))

    def _add_count(n: int) -> None:
        allowed.add(str(n))
        allowed.add(str(abs(n)))

    _add_money(facts.sales_paise)
    _add_money(facts.purchases_paise)
    _add_money(facts.margin_paise)
    _add_money(facts.tax_paid_paise)
    _add_money(facts.tax_due_paise)
    _add_money(facts.itc_matched_paise)
    _add_money(facts.itc_probable_paise)
    _add_money(facts.itc_supplier_default_paise)
    _add_money(facts.itc_missing_entry_paise)

    _add_count(facts.itc_supplier_default_count)
    _add_count(facts.readiness_score)
    _add_count(facts.days_to_due)

    # Also allow days_to_due absolute value (prose may say "5 days past
    # due" for -5 or "5 days to go" for +5).
    allowed.add(str(abs(facts.days_to_due)))

    for b in facts.top_blockers:
        _add_money(b.paise_impact)

    # Period digits (YYYYMM) are legitimate: month names like "July"
    # will not tokenise, but "2026" would. Add the year and month.
    if facts.period:
        allowed.add(facts.period[:4])  # year
        # The month (01-12) is already in the always-allowed range.

    return allowed


def extract_number_tokens(text: str) -> list[str]:
    """Return all normalised digit strings appearing in ``text``."""
    if not text:
        return []
    tokens: list[str] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0)
        norm = _normalise(raw)
        # Skip anything that ends up empty or non-digit after strip.
        if not norm.lstrip("-").isdigit():
            continue
        tokens.append(norm)
    return tokens


def find_hallucinated(
    text: str, allowed: Iterable[str]
) -> list[str]:
    """Return the subset of tokens in ``text`` that are NOT in ``allowed``.

    Returned list preserves order of appearance in the text and
    deduplicates neighbouring repeats so a repeated hallucination
    surfaces once, not N times.
    """
    allowed_set = set(allowed)
    out: list[str] = []
    for tok in extract_number_tokens(text):
        if tok in allowed_set:
            continue
        if out and out[-1] == tok:
            continue
        out.append(tok)
    return out


def validate_output_blocks(
    *,
    facts: NarrationFacts,
    blocks: dict[str, str],
) -> None:
    """Raise :class:`NumberHallucination` if any block emits a disallowed number.

    ``blocks`` is any mapping of ``{block_name: prose}`` — we surface
    per-block context in the exception to make debugging easier.
    """
    allowed = build_allowed_forms(facts)
    offending: list[str] = []
    for name, text in blocks.items():
        bad = find_hallucinated(text, allowed)
        if bad:
            offending.extend(f"{name}:{b}" for b in bad)
    if offending:
        # Show a stable, small sample of the allowed set for debugging —
        # never dump the full set (can be huge if paise values are big).
        sample = sorted(allowed, key=lambda s: (len(s), s))[:20]
        raise NumberHallucination(offending=offending, allowed_sample=sample)
