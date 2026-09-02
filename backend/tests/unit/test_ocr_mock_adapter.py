"""Unit tests for the deterministic mock OCR adapter.

Load-bearing properties tested here:

* Same input bytes → identical extraction (the mock is deterministic).
* The fixture-matching path returns the pinned high-confidence fields
  a demo run needs.
* Unknown bytes fall through to a synthetic extraction that is
  low-confidence and warns the CA not to accept blindly.
* The empty-upload path raises rather than emitting a silent all-nulls
  extraction — the API layer already 400s empty uploads, so this is a
  defense-in-depth check.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.ocr.adapter_mock import MockOcrAdapter
from app.ocr.types import InvoiceExtraction, OcrExtractionFailed


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ocr"
    / "fixtures"
    / "sample_invoice_1.txt"
)


def _read_fixture() -> bytes:
    return FIXTURE_PATH.read_bytes()


class TestMockAdapterDeterminism:
    def test_same_bytes_produce_same_extraction(self) -> None:
        content = b"any garbage bytes will do here for determinism"
        a = MockOcrAdapter().extract(
            content=content, filename="a.pdf", direction="purchase"
        )
        b = MockOcrAdapter().extract(
            content=content, filename="a.pdf", direction="purchase"
        )
        assert a == b

    def test_hash_is_sha256_of_content(self) -> None:
        content = b"deterministic hash test"
        out = MockOcrAdapter().extract(
            content=content, filename="x.pdf", direction="purchase"
        )
        assert out.source_content_hash == hashlib.sha256(content).hexdigest()
        assert out.source_bytes_size == len(content)


class TestFixtureMatch:
    def test_sample_invoice_1_returns_pinned_high_confidence_fields(self) -> None:
        content = _read_fixture()
        out = MockOcrAdapter().extract(
            content=content,
            filename="sample_invoice_1.txt",
            direction="purchase",
        )
        assert out.overall_confidence == 1.0
        assert out.supplier_gstin.value == "29ABCDE1234F1Z5"
        assert out.supplier_gstin.confidence == 1.0
        assert out.invoice_number.value == "INV-2026-0001"
        assert out.invoice_date.value == "2026-07-15"
        # Money in paise; sanity-check the arithmetic (₹10,000 * 9% = ₹900).
        assert out.taxable_value_paise.value == "1000000"
        assert out.cgst_paise.value == "90000"
        assert out.sgst_paise.value == "90000"
        assert out.igst_paise.value == "0"
        assert out.total_paise.value == "1180000"
        assert out.hsn_sac.value == "998311"
        assert out.warnings == ()


class TestUnknownBytesSyntheticFallback:
    def test_low_confidence_and_warning_present(self) -> None:
        out = MockOcrAdapter().extract(
            content=b"this is not a known fixture",
            filename="mystery.pdf",
            direction="purchase",
        )
        assert out.overall_confidence < 0.75  # below the review threshold
        assert any("no fixture matched" in w for w in out.warnings)
        # Synthetic values still populate — the review UI needs *something*
        # to render fields against, even if they are low-confidence.
        assert out.invoice_number.value is not None
        assert out.invoice_number.value.startswith("MOCK-")
        assert out.taxable_value_paise.value is not None
        # gstin is left None so the field renders as "please enter".
        assert out.supplier_gstin.value is None

    def test_synthetic_tax_arithmetic_is_internally_consistent(self) -> None:
        out = MockOcrAdapter().extract(
            content=b"another mystery",
            filename="x.pdf",
            direction="purchase",
        )
        taxable = int(out.taxable_value_paise.value or "0")
        cgst = int(out.cgst_paise.value or "0")
        sgst = int(out.sgst_paise.value or "0")
        total = int(out.total_paise.value or "0")
        # 9% CGST + 9% SGST → total = taxable * 1.18.
        assert cgst == taxable * 9 // 100
        assert sgst == cgst
        assert total == taxable + cgst + sgst


class TestEmptyUploadRaises:
    def test_empty_content_raises(self) -> None:
        with pytest.raises(OcrExtractionFailed):
            MockOcrAdapter().extract(
                content=b"", filename="empty.pdf", direction="purchase"
            )


class TestAdapterAttribution:
    def test_adapter_metadata_on_response(self) -> None:
        out = MockOcrAdapter().extract(
            content=b"attribution test",
            filename="a.pdf",
            direction="purchase",
        )
        assert out.adapter == "mock"
        assert out.adapter_version == "0.1.0"
        assert isinstance(out, InvoiceExtraction)
