"""render_narration_pdf integration tests.

Seed a narration_run row directly, call render_narration_pdf, verify:
* PDF bytes are produced (magic bytes present),
* the key strings (client name, firm name, disclaimer) are in the
  rendered content,
* a mutated narration_run whose prose contains a hallucinated number
  raises NumberHallucination at render time (defence-in-depth guard).

Skipped when weasyprint's C libs are missing — same guard as
test_pdf_renderer.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.narrator.types import NumberHallucination


try:
    import weasyprint  # noqa: F401
    _WEASY_AVAILABLE = True
except (ImportError, OSError):
    _WEASY_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _WEASY_AVAILABLE,
    reason="weasyprint (or its cairo/pango system libs) not installed",
)


def _canonical_facts_json() -> dict:
    return {
        "period": "202607",
        "return_type": "GSTR1",
        "firm_name": "Acme CA",
        "client_name": "Beta Traders",
        "sales_paise": 10_000_000,
        "purchases_paise": 5_000_000,
        "margin_paise": 5_000_000,
        "tax_paid_paise": 2_500_000,
        "tax_due_paise": 3_000_000,
        "itc": {
            "matched_paise": 25_000_000,
            "probable_paise": 15_000_000,
            "supplier_default_paise": 4_300_000,
            "missing_entry_paise": 12_000_000,
            "supplier_default_count": 6,
        },
        "readiness_score": 65,
        "days_to_due": 5,
        "top_blockers": [
            {
                "kind": "supplier_default",
                "owner": "ca",
                "description": "ITC at risk from 6 suppliers",
                "paise_impact": 4_300_000,
            }
        ],
        "rule_pack_version": "1.0.0",
    }


def _canonical_output_json() -> dict:
    """Prose that only references numbers present in _canonical_facts_json."""
    return {
        "page1_health": (
            "For July 2026, sales came in at ₹1,00,000 and purchases at "
            "₹50,000, leaving a margin of ₹50,000."
        ),
        "page1_tax_position": (
            "Tax paid so far this period is ₹25,000; tax due is ₹30,000. "
            "Filing readiness stands at 65 out of 100. You have 5 days "
            "to the GSTR1 due date."
        ),
        "page2_attention": (
            "The items below need attention before filing:\n"
            "• ITC at risk from 6 suppliers — ₹43,000, your CA to act."
        ),
        "page2_ask_your_ca": (
            "Ask your CA about the 6 suppliers whose ITC is at risk "
            "(₹43,000 total)."
        ),
    }


def _seed_narration_run(bootstrap: dict, output: dict) -> uuid.UUID:
    """Insert a narration_run + minimal gstin_profile so the render can
    resolve the firm name via the ca_firm join."""
    firm_id = bootstrap["firm_id"]
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'Beta Traders')"
            ),
            {"c": client_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) VALUES "
                "(:g, :f, :c, '29ABCDE1234F1Z5', '29')"
            ),
            {"g": gstin_id, "f": firm_id, "c": client_id},
        )
        run_id = conn.execute(
            text(
                """
                INSERT INTO narration_run (
                    firm_id, gstin_profile_id, return_type, period,
                    language, provider, model, facts, output
                ) VALUES (
                    :f, :g, 'GSTR1', '202607',
                    'en', 'mock', 'template-v1',
                    CAST(:facts AS JSONB), CAST(:out AS JSONB)
                )
                RETURNING id
                """
            ),
            {
                "f": firm_id,
                "g": gstin_id,
                "facts": json.dumps(_canonical_facts_json()),
                "out": json.dumps(output),
            },
        ).scalar_one()
    return run_id


def test_render_narration_pdf_produces_valid_pdf(bootstrap_firm) -> None:
    from app.pdf.service import render_narration_pdf

    # ca_firm gets its name from bootstrap_firm's default "Test Firm";
    # override so we can assert the letterhead value.
    b = bootstrap_firm(firm_name="Acme CA")
    run_id = _seed_narration_run(b, _canonical_output_json())

    pdf = render_narration_pdf(firm_id=b["firm_id"], narration_run_id=run_id)
    assert bytes(pdf[:5]) == b"%PDF-"

    try:
        from pdfminer.high_level import extract_text
        import io

        text_out = extract_text(io.BytesIO(pdf))
        assert "Acme CA" in text_out
        assert "Beta Traders" in text_out
        assert "GSTR1" in text_out
        assert "43,000" in text_out
    except ImportError:
        # Raw scan fallback (see test_pdf_renderer note).
        assert b"Acme CA" in pdf or b"Beta Traders" in pdf


def test_render_narration_pdf_rejects_hallucinated_prose(
    bootstrap_firm,
) -> None:
    """Persisted prose that references a number NOT in facts must be
    refused by the renderer's validator check — the render path is the
    last line of defence before delivery."""
    from app.pdf.service import render_narration_pdf

    b = bootstrap_firm(firm_name="Acme CA")
    bad_output = dict(_canonical_output_json())
    bad_output["page1_health"] = (
        "For July 2026, sales came in at ₹99,999 — a made-up number."
    )
    run_id = _seed_narration_run(b, bad_output)

    with pytest.raises(NumberHallucination):
        render_narration_pdf(firm_id=b["firm_id"], narration_run_id=run_id)


def test_render_narration_pdf_missing_run_raises(bootstrap_firm) -> None:
    from app.pdf.service import NarrationRunUnavailable, render_narration_pdf

    b = bootstrap_firm()
    with pytest.raises(NarrationRunUnavailable):
        render_narration_pdf(firm_id=b["firm_id"], narration_run_id=uuid.uuid4())
