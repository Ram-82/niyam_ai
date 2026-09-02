"""OCR adapter for scanned PDFs and photos, via Tesseract.

Handles the ~30% of invoices that arrive as photos or scanned PDFs
(WhatsApp forwards, phone snaps, scanner uploads). Text-native PDFs
should go through :mod:`app.ocr.adapter_pdfminer` instead — it's an
order of magnitude faster and doesn't need the tesseract binary.

Flow:

1. Detect input type from bytes magic + filename extension.
2. If PDF → pdf2image rasterises each page at 300 DPI to a PIL image.
   If image → open directly with PIL.
3. Run tesseract on each image, concatenate the extracted text.
4. Hand the text to :mod:`app.ocr.extractors` (same regex heuristics
   the pdfminer adapter uses — the extractor is intentionally
   agnostic to how the text was obtained).

The tesseract binary + poppler-utils system packages ship in the
backend Dockerfile. If either is missing at runtime,
:class:`OcrExtractionFailed` is raised with an operator-actionable
message rather than a raw ImportError.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Optional

from app.ocr.extractors import (
    extract_all_fields,
    rollup_confidence,
    tax_arithmetic_warning,
)
from app.ocr.types import (
    Direction,
    FieldConfidence,
    InvoiceExtraction,
    OcrAdapter,
    OcrExtractionFailed,
    OcrUnsupportedFormat,
)


log = logging.getLogger("niyam.ocr.adapter_tesseract")


_ADAPTER_NAME = "tesseract"
_ADAPTER_VERSION = "0.1.0"


# Rasterisation DPI. Tesseract's accuracy on Indian tax-invoice
# typography (mixed Devanagari + Latin, small fonts, tabular layout)
# plateaus around 300 DPI; going to 400 DPI doubles memory but adds
# little accuracy. Keep 300 unless a specific invoice class needs
# more.
_RASTER_DPI = 300


# Tesseract language pack list. English only for P2.1 Step 3b; the
# Dockerfile installs tesseract-ocr-eng. Adding Hindi/Kannada is a
# ``apt-get install tesseract-ocr-hin tesseract-ocr-kan`` in the
# Dockerfile + a config change; no code changes needed here.
_TESSERACT_LANGS = "eng"


# Image magic bytes.
_IMAGE_MAGIC = {
    b"\x89PNG\r\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"RIFF": "webp",  # WebP header is 'RIFF....WEBP'
}


def _detect_kind(content: bytes) -> str:
    """Return 'pdf' | 'image' | 'unknown'."""
    if b"%PDF-" in content[:8]:
        return "pdf"
    head = content[:6]
    for magic, _ in _IMAGE_MAGIC.items():
        if head.startswith(magic):
            return "image"
    # WebP: RIFF....WEBP (need to check byte 8-12 too).
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image"
    return "unknown"


class TesseractAdapter:
    """Tesseract-backed OCR for scans + photos. See module docstring."""

    adapter: str = _ADAPTER_NAME
    adapter_version: str = _ADAPTER_VERSION

    def extract(
        self,
        *,
        content: bytes,
        filename: str,
        direction: Direction,
    ) -> InvoiceExtraction:
        if not content:
            raise OcrExtractionFailed("empty upload; nothing to extract")

        kind = _detect_kind(content)
        if kind == "unknown":
            raise OcrUnsupportedFormat(
                "tesseract adapter received bytes that are neither a PDF nor "
                "a supported image (PNG / JPEG / WebP)"
            )

        # Late imports so a mock-mode deployment doesn't pay the
        # pdf2image + PIL import cost, and so a missing native binary
        # surfaces as OcrExtractionFailed rather than a raw ImportError
        # at module import time.
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
        except ImportError as e:
            raise OcrExtractionFailed(
                f"tesseract adapter missing python deps ({e}); "
                "install pytesseract + Pillow (see pyproject)"
            ) from e

        try:
            if kind == "pdf":
                images = _rasterise_pdf(content, dpi=_RASTER_DPI)
            else:
                images = [Image.open(io.BytesIO(content))]
        except Exception as e:
            log.warning("tesseract rasterisation failed: %s", e)
            raise OcrExtractionFailed(f"rasterisation failed: {e}") from e

        text_parts: list[str] = []
        for img in images:
            try:
                page_text = pytesseract.image_to_string(
                    img, lang=_TESSERACT_LANGS
                )
            except pytesseract.pytesseract.TesseractNotFoundError as e:
                raise OcrExtractionFailed(
                    "tesseract binary not found in PATH — install "
                    "tesseract-ocr (see backend Dockerfile)"
                ) from e
            except Exception as e:
                log.warning("tesseract OCR failed on a page: %s", e)
                raise OcrExtractionFailed(
                    f"tesseract OCR failed: {e}"
                ) from e
            text_parts.append(page_text)

        text = "\n".join(text_parts)
        if len(text.strip()) < 20:
            # OCR ran but returned effectively nothing — likely a
            # non-invoice image or a scan too poor to read.
            raise OcrExtractionFailed(
                "tesseract produced under 20 characters of text — "
                "image quality too low or not an invoice"
            )

        fields = extract_all_fields(text)
        digest = hashlib.sha256(content).hexdigest()
        warnings: list[str] = []

        def _int(fc: FieldConfidence) -> Optional[int]:
            if fc.value is None:
                return None
            try:
                return int(fc.value)
            except ValueError:
                return None

        arith = tax_arithmetic_warning(
            _int(fields["taxable_value_paise"]),
            _int(fields["cgst_paise"]),
            _int(fields["sgst_paise"]),
            _int(fields["igst_paise"]),
            _int(fields["total_paise"]),
        )
        if arith:
            warnings.append(arith)

        gstin = fields["supplier_gstin"]
        if gstin.value and gstin.confidence < 1.0:
            warnings.append(
                f"supplier GSTIN {gstin.value!r} did not pass all domain "
                "checks (structure/state-code/checksum) — please verify"
            )

        # OCR is inherently noisier than pdfminer — dampen the rollup
        # so the review UI's low-confidence threshold catches more
        # fields for CA review. A field that pdfminer would score 0.85
        # becomes 0.85 * 0.9 = 0.765 here — still above the default
        # 0.75 threshold so a good scan doesn't unnecessarily raise a
        # flag, but a marginal scan trips it.
        raw_rollup = rollup_confidence(fields)
        overall = round(raw_rollup * 0.9, 3)

        return InvoiceExtraction(
            adapter=_ADAPTER_NAME,
            adapter_version=_ADAPTER_VERSION,
            source_filename=filename,
            source_content_hash=digest,
            source_bytes_size=len(content),
            supplier_gstin=fields["supplier_gstin"],
            invoice_number=fields["invoice_number"],
            invoice_date=fields["invoice_date"],
            taxable_value_paise=fields["taxable_value_paise"],
            cgst_paise=fields["cgst_paise"],
            sgst_paise=fields["sgst_paise"],
            igst_paise=fields["igst_paise"],
            total_paise=fields["total_paise"],
            hsn_sac=fields["hsn_sac"],
            overall_confidence=overall,
            warnings=tuple(warnings),
        )


def _rasterise_pdf(pdf_bytes: bytes, *, dpi: int) -> list:
    """Turn PDF bytes into a list of PIL images (one per page)."""
    from pdf2image import convert_from_bytes  # type: ignore

    return convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")


# Module-level protocol check.
_: OcrAdapter = TesseractAdapter()
