"""GSTIN format + checksum.

**Algorithm** (per the widely-cited CBIC / GSTN checksum specification):

* 15 characters. Alphabet: ``0-9`` (values 0–9) then ``A-Z`` (values 10–35).
* Positions 0–13 are the base; position 14 is the check digit.
* For each position ``i`` in 0..13:
    factor = 1 if i is even (positions 1,3,5,... in 1-indexed convention),
             2 if i is odd
    product = value * factor
    Sum the base-36 digits of ``product`` (i.e. ``product // 36 + product % 36``)
    into a running total.
* Check digit value = ``(36 - total % 36) % 36``. Convert back to a char via
  the alphabet — that's the expected character at position 14.

Structural regex (also enforced by DB CHECK on ``gstin_profile.gstin``):

    ^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]$
      state    PAN                    entity Z checkdigit

We generate our own test vectors (``computed_gstin`` in tests) so the
algorithm is roundtrip-verified — a self-consistent implementation of a
published spec. Any deviation between our algorithm and the real GSTN
one will surface the moment a CA pastes a real GSTIN and gets a false
R002 flag. That's a marked ``TODO-VERIFY-WITH-CA`` in the rule pack.
"""
from __future__ import annotations

import re


GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_INDEX = {c: i for i, c in enumerate(GSTIN_ALPHABET)}
_STRUCTURAL_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]$"
)


def has_valid_structure(gstin: str) -> bool:
    """Cheap regex check — 15 chars, correct segments and character classes."""
    return isinstance(gstin, str) and bool(_STRUCTURAL_RE.match(gstin))


def compute_check_digit(base14: str) -> str:
    """Compute the 15th character for a 14-char GSTIN prefix.

    Raises ``ValueError`` if ``base14`` is not exactly 14 characters or
    contains a character outside the alphabet.
    """
    if len(base14) != 14:
        raise ValueError(f"expected 14 chars, got {len(base14)}")
    total = 0
    for i, c in enumerate(base14):
        v = _INDEX.get(c)
        if v is None:
            raise ValueError(f"invalid character {c!r} at position {i}")
        factor = 1 if i % 2 == 0 else 2
        product = v * factor
        total += product // 36 + product % 36
    return GSTIN_ALPHABET[(36 - total % 36) % 36]


def has_valid_checksum(gstin: str) -> bool:
    """True iff the 15th character equals the computed check digit."""
    if not has_valid_structure(gstin):
        return False
    try:
        return gstin[14] == compute_check_digit(gstin[:14])
    except ValueError:
        return False


def is_valid_gstin(gstin: str) -> bool:
    """Structure + checksum. Used by R002."""
    return has_valid_structure(gstin) and has_valid_checksum(gstin)


GSTIN_STATE_CODES: frozenset[str] = frozenset({
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24", "25", "26", "27", "29", "30", "31",
    "32", "33", "34", "35", "36", "37", "38", "97", "99",
})
"""39 statutory GSTN state/UT codes. 28 is absent: post-bifurcation AP
moved to 37; legacy 28 GSTINs are no longer issued by GSTN."""


def has_valid_state_code(gstin: str) -> bool:
    """True iff the first two characters are a recognised GSTN state/UT code."""
    return isinstance(gstin, str) and len(gstin) >= 2 and gstin[:2] in GSTIN_STATE_CODES


def state_code(gstin: str) -> str:
    """First two chars = numeric state code."""
    return gstin[:2]
