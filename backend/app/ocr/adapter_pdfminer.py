"""Text-native PDF extractor via pdfminer.six.

Handles the ~70% of invoices that arrive as text-native PDFs (exported
from Tally / Zoho / Busy Accounting / accounting software). Scanned
PDFs and photos need the Tesseract adapter (Step 3b) — the pdfminer
extractor will return an empty text buffer for those, and this
adapter raises :class:`OcrExtractionFailed` so the API layer surfaces
"couldn't read this document" rather than silently emitting a null
extraction the CA might accept by accident.
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


log = logging.getLogger("niyam.ocr.adapter_pdfminer")


_ADAPTER_NAME = "pdfminer"
_ADAPTER_VERSION = "0.1.0"


# Below this ratio of extracted text to file size we assume the PDF is
# a scanned image and route the CA to the Tesseract path (Step 3b).
# Empirical: text-native PDFs give ~1 char per 40-80 bytes; a scanned
# PDF at 300 DPI gives < 1 char per few thousand bytes.
_MIN_TEXT_PER_KB = 1.0


class PdfMinerAdapter:
    """pdfminer.six-backed extractor for text-native PDFs."""

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

        # pdfminer only handles PDFs. For images the API layer would
        # send them to a different adapter (Step 3b Tesseract) — but
        # if a caller wires the pdfminer adapter against a JPEG, fail
        # loud so the operator sees the misconfiguration.
        if not _looks_like_pdf(content):
            raise OcrUnsupportedFormat(
                "pdfminer adapter received non-PDF bytes; use the tesseract "
                "adapter for images (Step 3b)"
            )

        text = _extract_text_bytes(content)
        # Text-density gate — a scanned PDF yields little to no text.
        kb = max(1, len(content) // 1024)
        density = len(text) / kb
        if density < _MIN_TEXT_PER_KB:
            raise OcrExtractionFailed(
                f"pdfminer extracted only {len(text)} chars from {kb} KiB "
                f"(density {density:.2f} chars/KiB) — looks like a scanned "
                "PDF; the tesseract adapter (Step 3b) handles those"
            )

        fields = extract_all_fields(text)
        digest = hashlib.sha256(content).hexdigest()

        warnings: list[str] = []

        # Tax-arithmetic cross-check. Non-blocking; the validation
        # engine (R006) is the authoritative arithmetic rule at
        # accept-time — this is an eyeball advisory for the CA.
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

        # Loud advisory when the GSTIN check failed — the R002 rule
        # will fire at accept-time, but the CA benefits from seeing
        # it before they click Accept.
        gstin = fields["supplier_gstin"]
        if gstin.value and gstin.confidence < 1.0:
            warnings.append(
                f"supplier GSTIN {gstin.value!r} did not pass all domain "
                "checks (structure/state-code/checksum) — please verify"
            )

        overall = rollup_confidence(fields)

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


def _looks_like_pdf(content: bytes) -> bool:
    """PDF magic number is ``%PDF-``. Some banks/tools prepend a BOM,
    so allow it in the first 8 bytes."""
    head = content[:8]
    return b"%PDF-" in head


def _extract_text_bytes(pdf_bytes: bytes) -> str:
    """Local import for pdfminer so mock-mode deployments (which never
    call this) don't pay pdfminer's import cost."""
    from pdfminer.high_level import extract_text  # type: ignore

    try:
        return extract_text(io.BytesIO(pdf_bytes)) or ""
    except Exception as e:
        log.warning("pdfminer.extract_text failed: %s", e)
        raise OcrExtractionFailed(f"pdfminer extraction error: {e}") from e


# Module-level protocol check — trips at import time if the class
# stops satisfying the OcrAdapter interface.
_: OcrAdapter = PdfMinerAdapter()
