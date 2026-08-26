"""Data contracts for the OCR adapters.

The adapter's job is to take raw upload bytes (PDF or image) and return
a *draft* :class:`InvoiceExtraction` — a structural mirror of the
``invoice`` table's columns plus per-field confidence. Nothing persists
until a CA reviews and accepts the draft (that flow lands in P2.1
Step 4). The extraction is deliberately paise-typed to match the rest
of the money-handling code — decimal rupees stay out of the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional, Protocol


Direction = Literal["purchase", "sale"]


class OcrError(RuntimeError):
    """Base class for OCR failures."""


class OcrDisabled(OcrError):
    """Feature flag off. API returns 503; UI hides the upload widget."""


class OcrUnsupportedFormat(OcrError):
    """Upload extension / MIME type is not one the current adapter accepts."""


class OcrExtractionFailed(OcrError):
    """The adapter ran but could not produce a usable extraction — bad
    scan quality, unreadable PDF, non-invoice document, etc. The CA
    sees a 'could not read this document, try again' surface."""


@dataclass(frozen=True)
class FieldConfidence:
    """Per-field confidence score in [0.0, 1.0].

    Below ``ocr_low_confidence_threshold`` (default 0.75) the frontend
    highlights the field for CA review before acceptance. A 1.0 score
    from the mock adapter means "deterministic fixture, trust it";
    from a real adapter it means "layout-model + OCR both agreed and
    the value matched the expected regex".
    """

    value: Optional[str]
    confidence: float


@dataclass(frozen=True)
class InvoiceExtraction:
    """The draft extraction the CA reviews before it becomes an Invoice.

    Structural mirror of ``models.tables.Invoice`` (paise everywhere) so
    the acceptance flow in Step 4 can insert without a translation
    layer. All fields are optional at the type level because a real
    scan may fail to lift any one of them — the CA fills gaps by hand
    in the review UI.
    """

    # Adapter attribution — surfaces in the audit trail alongside every
    # extraction so a later CA can see which extractor produced these
    # numbers and re-run under a different one if quality regressed.
    adapter: str  # 'mock' | 'pdfminer' | 'tesseract' | ...
    adapter_version: str
    source_filename: str
    source_content_hash: str  # sha256 of the upload bytes
    source_bytes_size: int

    # Extracted invoice fields — each carries its own confidence.
    supplier_gstin: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    invoice_number: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    invoice_date: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    taxable_value_paise: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    cgst_paise: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    sgst_paise: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    igst_paise: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    total_paise: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))
    hsn_sac: FieldConfidence = field(default_factory=lambda: FieldConfidence(None, 0.0))

    # Overall confidence — the adapter's own rollup, NOT a mean of
    # per-field scores. A layout classifier that identifies the doc as
    # "definitely a tax invoice" contributes here even if some line
    # items are blank.
    overall_confidence: float = 0.0

    # Free-text warnings the CA should read before accepting. e.g.
    # "GSTIN checksum failed", "tax arithmetic off by ₹2 — rounding?",
    # "hsn code not present on invoice". Never blocking; strictly
    # advisory. The validation engine (R001..R009) is authoritative
    # for accept-time checks and runs when the Invoice row is created.
    warnings: tuple[str, ...] = field(default_factory=tuple)


class OcrAdapter(Protocol):
    """Adapter interface. Every extractor implements this.

    Adapters are pure — they receive bytes + filename and return an
    :class:`InvoiceExtraction`. Persistence and audit are the service
    layer's job, not the adapter's.
    """

    adapter: str
    adapter_version: str

    def extract(
        self,
        *,
        content: bytes,
        filename: str,
        direction: Direction,
    ) -> InvoiceExtraction:  # pragma: no cover
        ...
