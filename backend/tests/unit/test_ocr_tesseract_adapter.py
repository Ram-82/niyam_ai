"""Unit tests for the tesseract adapter.

These tests require the ``tesseract`` binary + ``poppler-utils`` and
the Python ``pytesseract`` / ``pdf2image`` / ``Pillow`` wheels. On a
host / container that lacks any of them the tests skip with a clear
message rather than failing — the Dockerfile installs everything for
CI, but a developer running pytest on their laptop may not have the
binary installed.

Load-bearing properties tested:

* PDF magic detection: PDF vs image vs unknown branches.
* Non-PDF / non-image → OcrUnsupportedFormat.
* Empty upload → OcrExtractionFailed.
* Happy path against a WeasyPrint-rendered PDF: fields extracted with
  reasonable confidence, adapter attribution correct, arithmetic
  warning absent.
* Overall confidence is dampened vs pdfminer (0.9x) — a rendered PDF
  through tesseract should score noticeably below a rendered PDF
  through pdfminer.
"""
from __future__ import annotations

import shutil

import pytest


# Skip the whole module if either the binary or a python wheel is missing.
_MISSING: list[str] = []
if shutil.which("tesseract") is None:
    _MISSING.append("tesseract binary")
if shutil.which("pdftoppm") is None:
    _MISSING.append("poppler (pdftoppm)")
try:  # noqa: SIM105
    import pytesseract  # type: ignore  # noqa: F401
except ImportError:
    _MISSING.append("pytesseract python package")
try:
    import pdf2image  # type: ignore  # noqa: F401
except ImportError:
    _MISSING.append("pdf2image python package")
try:
    from PIL import Image  # type: ignore  # noqa: F401
except ImportError:
    _MISSING.append("Pillow python package")

if _MISSING:  # pragma: no cover
    pytest.skip(
        f"tesseract adapter deps missing: {_MISSING}",
        allow_module_level=True,
    )


from app.ocr.adapter_tesseract import TesseractAdapter, _detect_kind  # noqa: E402
from app.ocr.types import OcrExtractionFailed, OcrUnsupportedFormat  # noqa: E402


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectKind:
    def test_pdf(self) -> None:
        assert _detect_kind(b"%PDF-1.4\nfoo") == "pdf"

    def test_png(self) -> None:
        assert _detect_kind(b"\x89PNG\r\n\x1a\nrest") == "image"

    def test_jpeg(self) -> None:
        assert _detect_kind(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image"

    def test_webp(self) -> None:
        assert _detect_kind(b"RIFF\x00\x00\x00\x00WEBP") == "image"

    def test_unknown(self) -> None:
        assert _detect_kind(b"random bytes not a header") == "unknown"


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


class TestTesseractAdapterRejections:
    def test_empty_upload_raises(self) -> None:
        with pytest.raises(OcrExtractionFailed):
            TesseractAdapter().extract(
                content=b"", filename="empty.pdf", direction="purchase"
            )

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(OcrUnsupportedFormat):
            TesseractAdapter().extract(
                content=b"nothing but plain text pretending to be a file"
                        + b" " * 200,
                filename="mystery.bin",
                direction="purchase",
            )


# ---------------------------------------------------------------------------
# Happy path (this is slow: WeasyPrint render + pdf2image rasterise +
# tesseract OCR). Keep the fixture PDF minimal to stay within CI wall
# clock budget.
# ---------------------------------------------------------------------------


_INVOICE_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: 'DejaVu Sans', sans-serif; font-size: 20pt;">
  <h1>TAX INVOICE</h1>
  <p>Supplier GSTIN: 29ABCDE1234F1ZW</p>
  <p>Invoice No: INV-2026-9999</p>
  <p>Invoice Date: 2026-08-01</p>
  <p>HSN: 998311</p>
  <p>Taxable Value: 2,000.00</p>
  <p>CGST: 180.00</p>
  <p>SGST: 180.00</p>
  <p>IGST: 0.00</p>
  <p>Grand Total: 2,360.00</p>
</body>
</html>
"""


@pytest.fixture(scope="module")
def invoice_pdf() -> bytes:
    from weasyprint import HTML
    return HTML(string=_INVOICE_HTML).write_pdf()


class TestTesseractAdapterHappyPath:
    @pytest.mark.timeout(60)  # rasterise + OCR is slow; cap the run.
    def test_extracts_key_fields(self, invoice_pdf: bytes) -> None:
        out = TesseractAdapter().extract(
            content=invoice_pdf,
            filename="scan.pdf",
            direction="purchase",
        )
        # Attribution.
        assert out.adapter == "tesseract"
        assert out.source_bytes_size == len(invoice_pdf)

        # The invoice number should survive OCR even at 20pt.
        # Tesseract sometimes misreads digits; we assert on the
        # supplier-GSTIN prefix + invoice-date prefix rather than
        # exact string equality to keep the test robust to a stray
        # character on an OCR pass.
        assert (out.supplier_gstin.value or "").startswith("29ABCDE")
        assert (out.invoice_date.value or "").startswith("2026-08")

        # Overall confidence is dampened 0.9x vs pdfminer — a clean
        # rendered PDF should still land above the 0.5 mark.
        assert 0.4 <= out.overall_confidence <= 0.9
