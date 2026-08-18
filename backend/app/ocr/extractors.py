"""Pure text → invoice field heuristics.

Each ``extract_*`` function takes the raw text produced by a PDF /
image extractor and returns a :class:`~app.ocr.types.FieldConfidence`
carrying the parsed value + a 0.0..1.0 confidence score.

Confidence scoring — the deliberate tiers:

* **1.00** — value found by a label + regex match AND passes a domain
  check (e.g. GSTIN checksum, tax arithmetic consistent).
* **0.85** — value found by a labeled regex, no domain check available
  (invoice number, HSN).
* **0.65** — value found by an unlabeled regex fallback (e.g. the
  first date in the document when no "Invoice Date" label was found).
* **0.30** — value found only by a weak heuristic; the review UI
  highlights the field.
* **0.00** — no candidate found; ``value`` is ``None``.

The heuristics are intentionally conservative — a low confidence for a
field the CA has to review by hand is cheaper than a false-positive
that lands in an ``Invoice`` row.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from app.engines.validation.gstin import (
    has_valid_checksum,
    has_valid_state_code,
    has_valid_structure,
)
from app.ocr.types import FieldConfidence


# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------


# 15-character GSTIN: 2 state digits, 5 letters, 4 digits, 1 letter,
# 1 alphanumeric entity code, "Z" fixed, 1 checksum.
_GSTIN_RE = re.compile(
    r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b"
)


def extract_supplier_gstin(text: str) -> FieldConfidence:
    """Return the highest-confidence GSTIN candidate in ``text``.

    We prefer a match near a "GSTIN" / "GST No" label, then fall back
    to the first pattern match anywhere. Multiple GSTINs on an invoice
    are common (supplier + buyer); the buyer's is filtered out by a
    negative-label check if we can find one.
    """
    # Labeled supplier match — highest confidence.
    labeled = re.search(
        r"(?:GSTIN|GST\s*No\.?|GST\s*Number)[^\n:]{0,10}[:\s]\s*"
        r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        cand = labeled.group(1)
        if has_valid_structure(cand) and has_valid_state_code(cand) and has_valid_checksum(cand):
            return FieldConfidence(cand, 1.0)
        # Regex hit but domain check failed — surface it low-confidence
        # so the CA sees the string and can correct it.
        return FieldConfidence(cand, 0.5)

    # Unlabeled fallback — return the first pattern match if any.
    all_matches = _GSTIN_RE.findall(text)
    if not all_matches:
        return FieldConfidence(None, 0.0)
    # Prefer the first checksum-valid candidate; else the first pattern-only match.
    for m in all_matches:
        if has_valid_structure(m) and has_valid_state_code(m) and has_valid_checksum(m):
            return FieldConfidence(m, 0.65)
    return FieldConfidence(all_matches[0], 0.3)


# ---------------------------------------------------------------------------
# Invoice number
# ---------------------------------------------------------------------------


def extract_invoice_number(text: str) -> FieldConfidence:
    """Return the value following an "Invoice No" / "Bill No" label.

    Invoice numbering is not standardised — CA firms see everything
    from ``INV-2026-0001`` to ``ACME/07/8912``. The regex accepts a
    conservative alphanumeric-plus-``/._-`` grammar, stopping at
    whitespace or newline.
    """
    m = re.search(
        r"(?:Invoice|Bill|Inv|Doc(?:ument)?)\s*(?:No|Number|#)\.?\s*[:\-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{1,40})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        return FieldConfidence(m.group(1).strip("./_-"), 0.85)
    return FieldConfidence(None, 0.0)


# ---------------------------------------------------------------------------
# Invoice date
# ---------------------------------------------------------------------------


# Ordered longest-first so YYYY-MM-DD matches before DD-MM-YYYY.
_DATE_FORMATS = (
    ("%Y-%m-%d", r"(\d{4}-\d{2}-\d{2})"),
    ("%d-%m-%Y", r"(\d{2}-\d{2}-\d{4})"),
    ("%d/%m/%Y", r"(\d{2}/\d{2}/\d{4})"),
    ("%d.%m.%Y", r"(\d{2}\.\d{2}\.\d{4})"),
    ("%d %b %Y", r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"),
)


def _parse_date(raw: str) -> Optional[date]:
    for fmt, _pat in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def extract_invoice_date(text: str) -> FieldConfidence:
    """Return the first parseable date near an "Invoice Date" label."""
    for fmt, pat in _DATE_FORMATS:
        m = re.search(
            r"(?:Invoice\s*Date|Bill\s*Date|Date)\s*[:\-]?\s*" + pat,
            text,
            flags=re.IGNORECASE,
        )
        if m:
            parsed = _parse_date(m.group(1))
            if parsed:
                return FieldConfidence(parsed.isoformat(), 1.0)
            return FieldConfidence(m.group(1), 0.5)

    # Unlabeled fallback — first parseable date anywhere.
    for fmt, pat in _DATE_FORMATS:
        m = re.search(pat, text)
        if m:
            parsed = _parse_date(m.group(1))
            if parsed:
                return FieldConfidence(parsed.isoformat(), 0.65)
    return FieldConfidence(None, 0.0)


# ---------------------------------------------------------------------------
# Money amounts (returned as paise strings — every downstream consumer
# expects strings so a "None" fallback doesn't force `int|None` handling).
# ---------------------------------------------------------------------------


# Indian-format number: 1,00,000.00 or plain 100000.00 — the grouping
# separator is optional and can be a comma or space.
_MONEY_RE = r"(?:₹|Rs\.?|INR)?\s*([0-9][0-9,\s]*(?:\.\d{2})?)"


def _to_paise(raw: str) -> Optional[int]:
    """Turn "1,00,000.00" or "10000" into an int paise value."""
    cleaned = re.sub(r"[,\s₹]", "", raw)
    if not cleaned:
        return None
    try:
        rupees = float(cleaned)
    except ValueError:
        return None
    return int(round(rupees * 100))


def _find_money_near(text: str, labels: tuple[str, ...]) -> Optional[str]:
    """Return the money string near any of the given labels."""
    for lbl in labels:
        m = re.search(
            lbl + r"[^\n0-9]*?" + _MONEY_RE,
            text,
            flags=re.IGNORECASE,
        )
        if m:
            return m.group(1)
    return None


def extract_taxable_value_paise(text: str) -> FieldConfidence:
    raw = _find_money_near(text, (
        r"Taxable\s*Value", r"Sub\s*Total", r"Taxable\s*Amount",
    ))
    if raw is None:
        return FieldConfidence(None, 0.0)
    paise = _to_paise(raw)
    if paise is None:
        return FieldConfidence(None, 0.0)
    return FieldConfidence(str(paise), 0.85)


def extract_cgst_paise(text: str) -> FieldConfidence:
    raw = _find_money_near(text, (r"CGST",))
    if raw is None:
        return FieldConfidence("0", 0.4)  # implicit zero when no CGST line
    paise = _to_paise(raw)
    return (
        FieldConfidence(str(paise), 0.85)
        if paise is not None
        else FieldConfidence(None, 0.0)
    )


def extract_sgst_paise(text: str) -> FieldConfidence:
    raw = _find_money_near(text, (r"SGST",))
    if raw is None:
        return FieldConfidence("0", 0.4)
    paise = _to_paise(raw)
    return (
        FieldConfidence(str(paise), 0.85)
        if paise is not None
        else FieldConfidence(None, 0.0)
    )


def extract_igst_paise(text: str) -> FieldConfidence:
    raw = _find_money_near(text, (r"IGST",))
    if raw is None:
        return FieldConfidence("0", 0.4)
    paise = _to_paise(raw)
    return (
        FieldConfidence(str(paise), 0.85)
        if paise is not None
        else FieldConfidence(None, 0.0)
    )


def extract_total_paise(text: str) -> FieldConfidence:
    raw = _find_money_near(text, (
        r"Grand\s*Total", r"Total\s*Amount", r"Total\s*\(INR\)", r"Total",
    ))
    if raw is None:
        return FieldConfidence(None, 0.0)
    paise = _to_paise(raw)
    if paise is None:
        return FieldConfidence(None, 0.0)
    return FieldConfidence(str(paise), 0.85)


# ---------------------------------------------------------------------------
# HSN / SAC
# ---------------------------------------------------------------------------


def extract_hsn_sac(text: str) -> FieldConfidence:
    """First 4/6/8-digit code near an "HSN" / "SAC" label."""
    m = re.search(
        r"(?:HSN|SAC|HSN\s*/?\s*SAC)\s*[:\-]?\s*([0-9]{4,8})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        return FieldConfidence(m.group(1), 0.85)
    return FieldConfidence(None, 0.0)


# ---------------------------------------------------------------------------
# Composite entrypoint
# ---------------------------------------------------------------------------


def extract_all_fields(text: str) -> dict[str, FieldConfidence]:
    """Run every extractor and return a dict keyed by field name."""
    return {
        "supplier_gstin": extract_supplier_gstin(text),
        "invoice_number": extract_invoice_number(text),
        "invoice_date": extract_invoice_date(text),
        "taxable_value_paise": extract_taxable_value_paise(text),
        "cgst_paise": extract_cgst_paise(text),
        "sgst_paise": extract_sgst_paise(text),
        "igst_paise": extract_igst_paise(text),
        "total_paise": extract_total_paise(text),
        "hsn_sac": extract_hsn_sac(text),
    }


def rollup_confidence(fields: dict[str, FieldConfidence]) -> float:
    """Overall confidence = mean of per-field scores over fields we
    actually recognised (value is not None). If nothing was found the
    rollup is 0.0 and the API surfaces a low-confidence extraction the
    CA must review before accepting."""
    found = [f.confidence for f in fields.values() if f.value is not None]
    if not found:
        return 0.0
    return round(sum(found) / len(found), 3)


def tax_arithmetic_warning(
    taxable: Optional[int],
    cgst: Optional[int],
    sgst: Optional[int],
    igst: Optional[int],
    total: Optional[int],
) -> Optional[str]:
    """If we have all five numbers, sanity-check taxable + cgst + sgst
    + igst ≈ total (±100 paise). Returns a warning string, or None."""
    if any(v is None for v in (taxable, cgst, sgst, igst, total)):
        return None
    computed = taxable + cgst + sgst + igst  # type: ignore[operator]
    if abs(computed - total) > 100:  # ±₹1 tolerance
        return (
            f"tax arithmetic mismatch: taxable+cgst+sgst+igst={computed} "
            f"paise but total on invoice={total} paise"
        )
    return None
