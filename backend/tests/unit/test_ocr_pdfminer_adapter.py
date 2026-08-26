"""Unit tests for the pdfminer adapter.

Load-bearing property: an adapter that receives a text-native PDF with
well-labeled invoice fields returns high-confidence per-field values
and no arithmetic warning. A scanned-PDF-shaped input (empty text
buffer) raises OcrExtractionFailed so the API can route the CA to the
tesseract path (Step 3b, not yet built).

The fixture PDF is generated at session scope via WeasyPrint so the
test suite does not carry binary artifacts in the repo. WeasyPrint +
pdfminer are already runtime dependencies, so no extra install cost.
"""
from __future__ import annotations

import pytest

from app.ocr.adapter_pdfminer import PdfMinerAdapter
from app.ocr.types import OcrExtractionFailed, OcrUnsupportedFormat


# ---------------------------------------------------------------------------
# Fixture PDFs
# ---------------------------------------------------------------------------


_HAPPY_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Tax Invoice</title></head>
<body style="font-family: sans-serif;">
  <h1>TAX INVOICE</h1>
  <p><b>Supplier:</b> ACME Traders Pvt Ltd</p>
  <p><b>GSTIN:</b> 29ABCDE1234F1ZW</p>
  <p><b>Buyer:</b> Beta Industries LLP</p>
  <p><b>Invoice No:</b> INV-2026-0001</p>
  <p><b>Invoice Date:</b> 2026-07-15</p>
  <p>Description: Consulting services (HSN: 998311)</p>
  <p>Taxable Value: 10,000.00</p>
  <p>CGST: 900.00</p>
  <p>SGST: 900.00</p>
  <p>IGST: 0.00</p>
  <p>Grand Total: 11,800.00</p>
</body>
</html>
"""


_ARITHMETIC_MISMATCH_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: sans-serif;">
  <p>Supplier GSTIN: 29ABCDE1234F1ZW</p>
  <p>Invoice No: INV-9</p>
  <p>Invoice Date: 2026-07-15</p>
  <p>Taxable Value: 10,000.00</p>
  <p>CGST: 900.00</p>
  <p>SGST: 900.00</p>
  <p>IGST: 0.00</p>
  <!-- Deliberately wrong: 10000 + 900 + 900 = 11800; total says 12000 -->
  <p>Grand Total: 12,000.00</p>
</body>
</html>
"""


@pytest.fixture(scope="session")
def happy_pdf_bytes() -> bytes:
    from weasyprint import HTML  # local — only paid when this test runs
    return HTML(string=_HAPPY_HTML).write_pdf()


@pytest.fixture(scope="session")
def arithmetic_mismatch_pdf_bytes() -> bytes:
    from weasyprint import HTML
    return HTML(string=_ARITHMETIC_MISMATCH_HTML).write_pdf()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPdfMinerAdapterHappyPath:
    def test_extracts_all_fields_at_high_confidence(self, happy_pdf_bytes: bytes) -> None:
        out = PdfMinerAdapter().extract(
            content=happy_pdf_bytes,
            filename="acme_invoice.pdf",
            direction="purchase",
        )
        assert out.adapter == "pdfminer"
        assert out.source_filename == "acme_invoice.pdf"
        assert out.source_bytes_size == len(happy_pdf_bytes)

        # GSTIN — labeled + checksum valid → 1.0.
        assert out.supplier_gstin.value == "29ABCDE1234F1ZW"
        assert out.supplier_gstin.confidence == 1.0

        # Invoice number + date.
        assert out.invoice_number.value == "INV-2026-0001"
        assert out.invoice_date.value == "2026-07-15"

        # Money — paise math.
        assert out.taxable_value_paise.value == "1000000"
        assert out.cgst_paise.value == "90000"
        assert out.sgst_paise.value == "90000"
        assert out.igst_paise.value == "0"
        assert out.total_paise.value == "1180000"

        assert out.hsn_sac.value == "998311"

        # Arithmetic is consistent → no warning.
        assert out.warnings == ()

        # Overall confidence should be high (many labeled matches).
        assert out.overall_confidence >= 0.85


class TestPdfMinerAdapterArithmeticWarning:
    def test_arithmetic_mismatch_surfaces_as_warning(
        self, arithmetic_mismatch_pdf_bytes: bytes
    ) -> None:
        out = PdfMinerAdapter().extract(
            content=arithmetic_mismatch_pdf_bytes,
            filename="bad_arith.pdf",
            direction="purchase",
        )
        assert any("mismatch" in w for w in out.warnings)


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


class TestPdfMinerAdapterRejections:
    def test_empty_upload_raises(self) -> None:
        with pytest.raises(OcrExtractionFailed):
            PdfMinerAdapter().extract(
                content=b"", filename="empty.pdf", direction="purchase"
            )

    def test_non_pdf_raises_unsupported_format(self) -> None:
        # A JPEG magic number ("\xff\xd8\xff") is not a PDF header.
        with pytest.raises(OcrUnsupportedFormat):
            PdfMinerAdapter().extract(
                content=b"\xff\xd8\xff\xe0" + b"fake jpeg body" * 200,
                filename="photo.jpg",
                direction="purchase",
            )

    def test_scanned_pdf_low_text_density_raises(self) -> None:
        # A minimal PDF header with only whitespace inside — pdfminer
        # extracts nothing, the density gate fires.
        minimal = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        # Pad to > 1 KiB so the density calculation isn't clamped.
        minimal += b"0" * 2000
        with pytest.raises(OcrExtractionFailed):
            PdfMinerAdapter().extract(
                content=minimal,
                filename="scanned.pdf",
                direction="purchase",
            )
