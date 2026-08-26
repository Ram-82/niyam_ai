"""Deterministic mock OCR adapter.

The mock exists so the whole P2.1 pipeline — API, feature flag, tests,
frontend upload widget, review UI — can be built + demoed end-to-end
before the real extractor lands. Rules:

* Same input bytes → identical extraction. The output is hashed off
  the SHA-256 of the upload so tests can assert against known values.
* Overall confidence is 1.0 — the mock is truthful about the fact
  that it is a mock (adapter='mock' in the response), so a caller
  that wants to know "was this a real read?" checks ``adapter``, not
  the confidence score.
* No file parsing. The mock accepts any bytes and any filename; it
  does not read PDFs. That is deliberate — real PDF handling is a
  separate concern being built in P2.1 Step 3.

Fixture library: if the upload's SHA-256 matches a known fixture
under :mod:`app.ocr.fixtures` we return the fixture's extraction
verbatim, so a demo run against sample_invoice_1.pdf produces the
"real" expected fields. Unknown bytes fall through to a synthetic
extraction derived from the hash so downstream code always sees a
well-shaped response.
"""
from __future__ import annotations

import hashlib
from datetime import date

from app.ocr.types import (
    Direction,
    FieldConfidence,
    InvoiceExtraction,
    OcrAdapter,
)


_ADAPTER_NAME = "mock"
_ADAPTER_VERSION = "0.1.0"


# Fixture library. Keyed by sha256 of the upload bytes. Real fixture
# files live under app/ocr/fixtures/; the hash below is computed once
# and pinned here so tests don't need to read the fixture file to know
# which extraction to expect.
#
# To add a fixture: drop the file under fixtures/, run
#   python -c "import hashlib; print(hashlib.sha256(open('backend/app/ocr/fixtures/FILE','rb').read()).hexdigest())"
# and paste the hash + expected extraction below.
_FIXTURE_EXTRACTIONS: dict[str, dict] = {
    # sample_invoice_1.txt — a text-based placeholder used until Step 3
    # ships real PDF handling. Its content is a plain-text mock invoice
    # so the hash is stable and the test asserts against the values
    # inline here.
    "93c519be50f4a73239bdbe1df576d49c85a4ba84dc94838f8b8096b3519e0838": {
        "supplier_gstin": ("29ABCDE1234F1Z5", 1.0),
        "invoice_number": ("INV-2026-0001", 1.0),
        "invoice_date": ("2026-07-15", 1.0),
        "taxable_value_paise": ("1000000", 1.0),  # ₹10,000.00
        "cgst_paise": ("90000", 1.0),             # ₹900.00
        "sgst_paise": ("90000", 1.0),
        "igst_paise": ("0", 1.0),
        "total_paise": ("1180000", 1.0),          # ₹11,800.00
        "hsn_sac": ("998311", 1.0),
        "overall_confidence": 1.0,
        "warnings": (),
    },
}


class MockOcrAdapter:
    """Deterministic OCR mock. See module docstring."""

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
            # An adapter that received zero bytes is a caller bug. Raise
            # rather than emit an empty extraction — the API layer
            # already rejects empty uploads with 400 before reaching here.
            from app.ocr.types import OcrExtractionFailed

            raise OcrExtractionFailed("empty upload; nothing to extract")

        digest = hashlib.sha256(content).hexdigest()

        if digest in _FIXTURE_EXTRACTIONS:
            fx = _FIXTURE_EXTRACTIONS[digest]
            return InvoiceExtraction(
                adapter=_ADAPTER_NAME,
                adapter_version=_ADAPTER_VERSION,
                source_filename=filename,
                source_content_hash=digest,
                source_bytes_size=len(content),
                supplier_gstin=FieldConfidence(*fx["supplier_gstin"]),
                invoice_number=FieldConfidence(*fx["invoice_number"]),
                invoice_date=FieldConfidence(*fx["invoice_date"]),
                taxable_value_paise=FieldConfidence(*fx["taxable_value_paise"]),
                cgst_paise=FieldConfidence(*fx["cgst_paise"]),
                sgst_paise=FieldConfidence(*fx["sgst_paise"]),
                igst_paise=FieldConfidence(*fx["igst_paise"]),
                total_paise=FieldConfidence(*fx["total_paise"]),
                hsn_sac=FieldConfidence(*fx["hsn_sac"]),
                overall_confidence=float(fx["overall_confidence"]),
                warnings=tuple(fx["warnings"]),
            )

        # Unknown bytes → synthetic extraction derived from the hash.
        # Downstream code sees a well-shaped response but the numbers
        # are marked low-confidence so a review-UI test that surfaces
        # them for CA edit is still exercised.
        # Derive stable pseudo-numbers from the hash so re-runs match.
        base = int(digest[:8], 16)
        taxable = (base % 900_000) + 100_000  # 100000..999999 paise
        cgst = taxable * 9 // 100
        sgst = cgst
        total = taxable + cgst + sgst
        synth_invoice_no = f"MOCK-{digest[:6].upper()}"
        return InvoiceExtraction(
            adapter=_ADAPTER_NAME,
            adapter_version=_ADAPTER_VERSION,
            source_filename=filename,
            source_content_hash=digest,
            source_bytes_size=len(content),
            supplier_gstin=FieldConfidence(None, 0.3),
            invoice_number=FieldConfidence(synth_invoice_no, 0.6),
            invoice_date=FieldConfidence(date.today().isoformat(), 0.4),
            taxable_value_paise=FieldConfidence(str(taxable), 0.5),
            cgst_paise=FieldConfidence(str(cgst), 0.5),
            sgst_paise=FieldConfidence(str(sgst), 0.5),
            igst_paise=FieldConfidence("0", 0.5),
            total_paise=FieldConfidence(str(total), 0.5),
            hsn_sac=FieldConfidence(None, 0.2),
            overall_confidence=0.45,
            warnings=(
                "mock adapter: no fixture matched, values are synthetic — "
                "do not accept without CA review",
            ),
        )


# Module-level protocol check — trips at import time if the class
# stops satisfying the OcrAdapter interface.
_: OcrAdapter = MockOcrAdapter()
