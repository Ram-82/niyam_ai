"""GSTIN structure + checksum tests.

We generate our own test vectors by:
  1. Choosing a 14-char base with valid segments.
  2. Computing the check digit with our algorithm.
  3. Asserting the resulting 15-char string passes ``is_valid_gstin``.

Roundtrip proves the algorithm is self-consistent. Cross-validating
against a real GSTN-issued GSTIN is on the Domain-verification list
(the rule_pack notes carry the same TODO).
"""
from __future__ import annotations

import pytest

from app.engines.validation.gstin import (
    compute_check_digit,
    has_valid_checksum,
    has_valid_structure,
    is_valid_gstin,
    state_code,
)


# 14-char valid bases (state + 5 PAN letters + 4 digits + 1 letter +
# 1 entity char + 'Z').
BASES = [
    "29AAAAA0000A1Z",
    "27BBBBB1234C2Z",
    "07XYZAB9999K9Z",
    "06AAAAA0000A9Z",
]


@pytest.mark.parametrize("base", BASES)
def test_valid_when_checksum_matches(base: str) -> None:
    cd = compute_check_digit(base)
    gstin = base + cd
    assert has_valid_structure(gstin), f"{gstin} failed structure"
    assert has_valid_checksum(gstin), f"{gstin} failed checksum"
    assert is_valid_gstin(gstin)


@pytest.mark.parametrize("base", BASES)
def test_invalid_when_checksum_wrong(base: str) -> None:
    cd = compute_check_digit(base)
    # Bump to the next char in the alphabet — guaranteed to differ.
    from app.engines.validation.gstin import GSTIN_ALPHABET
    wrong = GSTIN_ALPHABET[(GSTIN_ALPHABET.index(cd) + 1) % 36]
    gstin = base + wrong
    assert has_valid_structure(gstin)  # structure still valid
    assert not has_valid_checksum(gstin)
    assert not is_valid_gstin(gstin)


def test_structure_rejects_wrong_length() -> None:
    assert not has_valid_structure("29AAAAA0000A1Z")  # 14
    assert not has_valid_structure("29AAAAA0000A1Z55")  # 16
    assert not has_valid_structure("")


def test_structure_rejects_lowercase() -> None:
    assert not has_valid_structure("29aaaaa0000a1z5")


def test_structure_rejects_wrong_segment_shape() -> None:
    # PAN segment (positions 2-6) must be uppercase letters.
    assert not has_valid_structure("29AAA1A0000A1Z5")  # digit in PAN letters


def test_position_13_disallows_zero_entity_code() -> None:
    # Entity code (position 13, 0-indexed 12) must be [1-9A-Z], not 0.
    assert not has_valid_structure("29AAAAA0000A0Z5")


def test_state_code_extracted() -> None:
    assert state_code("29AAAAA0000A1Z5") == "29"


def test_compute_check_digit_deterministic() -> None:
    assert compute_check_digit("29AAAAA0000A1Z") == compute_check_digit("29AAAAA0000A1Z")


def test_compute_check_digit_rejects_bad_length() -> None:
    with pytest.raises(ValueError):
        compute_check_digit("SHORT")


def test_compute_check_digit_rejects_bad_char() -> None:
    with pytest.raises(ValueError):
        compute_check_digit("29AAAAA0000A1z")  # lowercase 'z'
