"""PDF renderer smoke tests.

These verify the renderer produces syntactically valid PDF bytes for a
canonical facts + narration payload. Deeper "does the layout look
right" checks live in visual review — not the test suite.

Skipped when WeasyPrint's cairo/pango system libs are missing (import
of the ``weasyprint`` module itself raises OSError in that state).
Runs cleanly inside the docker backend image which apt-installs the
stack.
"""
from __future__ import annotations

import re

import pytest


try:
    import weasyprint  # noqa: F401
    _WEASY_AVAILABLE = True
except (ImportError, OSError):
    _WEASY_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _WEASY_AVAILABLE,
    reason="weasyprint (or its cairo/pango system libs) not installed",
)


def _canonical_context() -> dict:
    """A facts + narration payload with the same numeric shape the
    validator would accept — every rupee figure in the prose blocks
    exists in the facts dict."""
    return {
        "firm_name": "Acme CA & Associates",
        "client_name": "Beta Traders",
        "period_label": "July 2026",
        "return_type": "GSTR1",
        "language": "en",
        "narration": {
            "page1_health": (
                "For July 2026, sales came in at ₹1,00,000 and purchases "
                "at ₹50,000, leaving a margin of ₹50,000."
            ),
            "page1_tax_position": (
                "Tax paid so far this period is ₹25,000; tax due is "
                "₹30,000. Filing readiness stands at 65 out of 100."
            ),
            "page2_attention": (
                "• ITC at risk from 6 suppliers — ₹43,000, your CA to act."
            ),
            "page2_ask_your_ca": (
                "Ask your CA about the 6 suppliers whose ITC is at risk "
                "(₹43,000 total)."
            ),
        },
        "facts": {
            "sales_paise": 100 * 100 * 1000,      # ₹1,00,000
            "purchases_paise": 50 * 100 * 1000,   # ₹50,000
            "margin_paise": 50 * 100 * 1000,      # ₹50,000
            "tax_paid_paise": 25 * 100 * 1000,    # ₹25,000
            "tax_due_paise": 30 * 100 * 1000,     # ₹30,000
            "itc": {
                "matched_paise": 250 * 100 * 1000,   # ₹2,50,000
                "probable_paise": 150 * 100 * 1000,  # ₹1,50,000
                "supplier_default_paise": 43 * 100 * 1000,  # ₹43,000
                "missing_entry_paise": 120 * 100 * 1000,    # ₹1,20,000
            },
            "readiness_score": 65,
            "days_to_due": 5,
            "rule_pack_version": "1.0.0",
        },
        "generated_at": "05 Aug 2026 12:00 UTC",
    }


def test_render_produces_pdf_magic_bytes() -> None:
    from app.pdf.renderer import render_template_to_pdf

    pdf = render_template_to_pdf("two_pager.html", _canonical_context())
    assert isinstance(pdf, (bytes, bytearray)), "renderer must return bytes"
    assert bytes(pdf[:5]) == b"%PDF-", (
        f"Not a valid PDF; first 5 bytes: {pdf[:5]!r}"
    )


def test_render_contains_two_pages() -> None:
    """The template hard-codes a page break between health/tax and
    attention/ask. Count the ``/Type /Page`` markers as a coarse
    page-count check (not a hard-parse but enough to catch a bug
    that collapses the doc to a single page)."""
    from app.pdf.renderer import render_template_to_pdf

    pdf = render_template_to_pdf("two_pager.html", _canonical_context())
    page_markers = re.findall(rb"/Type\s*/Page[^s]", pdf)
    assert len(page_markers) >= 2, (
        f"Expected at least 2 pages, got {len(page_markers)} markers"
    )


def test_render_includes_firm_and_client_names() -> None:
    """The names must appear in the PDF byte stream. PDF content is
    compressed by default so we render with the fact that WeasyPrint
    embeds text; a substring check on the raw bytes is fragile — we
    instead trust the template-rendering step which produced the HTML,
    and verify via pdfminer if it's importable. Fall back to a bytes
    check when pdfminer isn't installed."""
    from app.pdf.renderer import render_template_to_pdf

    pdf = render_template_to_pdf("two_pager.html", _canonical_context())
    try:
        from pdfminer.high_level import extract_text
        import io

        text = extract_text(io.BytesIO(pdf))
        assert "Acme CA" in text
        assert "Beta Traders" in text
        assert "₹43,000" in text or "43,000" in text
    except ImportError:
        # No pdfminer — do a raw scan (works because WeasyPrint doesn't
        # compress in the default configuration for small docs; if it
        # ever does, this fallback will fail and pdfminer becomes a
        # test dep).
        assert b"Acme CA" in pdf or b"Beta Traders" in pdf, (
            "Neither firm nor client name found in PDF; may need pdfminer test dep"
        )


def test_render_prose_disclaimer_present() -> None:
    """The 'Before credit/debit note adjustments' disclaimer is the
    load-bearing honesty label the whole product depends on."""
    from app.pdf.renderer import render_template_to_pdf

    pdf = render_template_to_pdf("two_pager.html", _canonical_context())
    try:
        from pdfminer.high_level import extract_text
        import io

        text = extract_text(io.BytesIO(pdf)).lower()
        assert "before credit/debit note adjustments" in text
    except ImportError:
        # Raw fallback.
        assert (
            b"before credit/debit note adjustments" in pdf
            or b"Before credit/debit note adjustments" in pdf
        )


def test_rupees_filter_indian_grouping() -> None:
    from app.pdf.renderer import _rupees_filter

    assert _rupees_filter(4_300_000) == "₹43,000"       # ₹43,000
    assert _rupees_filter(1_50_00_000) == "₹1,50,000"   # ₹1,50,000
    assert _rupees_filter(0) == "₹0"
    assert _rupees_filter(-4_300_000) == "₹-43,000"
    assert _rupees_filter(None) == "—"
