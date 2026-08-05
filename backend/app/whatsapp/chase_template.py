"""Supplier chase template renderer.

Produces the exact prose the supplier will receive so the CA can
eyeball it in the chase modal before hitting Approve & Send.

Template scope in P2:
* One canonical chase body per language (en/hi/kn/mr). The Meta
  template on the sender WABA carries a matching placeholder shape;
  we render the placeholders here so the CA sees what the supplier
  will read.
* Numbers (amount, invoice number) are threaded from the match_result
  / invoice — never invented.
* Firm name appears verbatim from ca_firm.name (so the "message from
  your CA firm" positioning holds).

Deliberately non-configurable in P2. Once a pilot firm asks for a
firm-specific tone we add a ``firm.chase_template_override`` column
and read from it here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ChaseLanguage = Literal["en", "hi", "kn", "mr"]


@dataclass(frozen=True)
class ChaseTemplateContext:
    firm_name: str
    supplier_name: str
    supplier_gstin: str
    invoice_number: str
    invoice_date_iso: str
    invoice_amount_paise: int


def _rupees(paise: int) -> str:
    """Whole-rupee ₹N,NN,NNN Indian grouping. Kept identical to the
    formatter used by :mod:`app.pdf.renderer` so numbers on the chase
    preview match numbers on the report PDF."""
    if paise is None:
        return "—"
    negative = paise < 0
    p = abs(int(paise))
    rupees = (p + 50) // 100
    s = str(rupees)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.append(rest[-2:])
            rest = rest[:-2]
        parts.append(rest)
        grouped = ",".join(reversed(parts)) + "," + last3
    sign = "-" if negative else ""
    return f"₹{sign}{grouped}"


def _short_date(iso: str) -> str:
    """Prefer ``15 Jun 2026`` over ISO. Falls back to the raw string
    if parsing fails so a malformed date does not raise."""
    from datetime import date

    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%d %b %Y")
    except (TypeError, ValueError):
        return iso


# The body templates. Kept short and factual — the message is a
# reminder, not a demand.
_TEMPLATES: dict[str, str] = {
    "en": (
        "Namaste {supplier_name},\n\n"
        "This is a reminder from {firm_name} on behalf of our client. "
        "The invoice {invoice_number} dated {invoice_date}, for "
        "{amount}, does not appear in the current GSTR-2B download. "
        "If you have not yet filed the corresponding GSTR-1 for this "
        "invoice, please do so at your earliest convenience so the "
        "input tax credit can be claimed.\n\n"
        "GSTIN: {supplier_gstin}\n\n"
        "Sent by {firm_name}."
    ),
    "hi": (
        "नमस्ते {supplier_name},\n\n"
        "{firm_name} से यह अनुस्मारक है — हमारे क्लाइंट की ओर से. "
        "इनवॉइस {invoice_number}, दिनांक {invoice_date}, राशि {amount}, "
        "वर्तमान GSTR-2B में नहीं आई है. यदि आपने अभी तक इसका "
        "GSTR-1 दाखिल नहीं किया है, कृपया शीघ्रता से करें ताकि ITC "
        "क्लेम हो सके.\n\n"
        "GSTIN: {supplier_gstin}\n\n"
        "प्रेषक: {firm_name}."
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {supplier_name},\n\n"
        "ಇದು {firm_name} ರಿಂದ ನಮ್ಮ ಗ್ರಾಹಕರ ಪರವಾಗಿ ನೆನಪಿಸುವಿಕೆಯಾಗಿದೆ. "
        "{invoice_date} ದಿನಾಂಕದ ಇನ್‌ವಾಯ್ಸ್ {invoice_number}, ಮೊತ್ತ "
        "{amount}, ಪ್ರಸ್ತುತ GSTR-2B ನಲ್ಲಿ ಕಂಡುಬರುತ್ತಿಲ್ಲ. ಇನ್ನೂ GSTR-1 "
        "ಸಲ್ಲಿಸದೇ ಇದ್ದರೆ ದಯವಿಟ್ಟು ಆದಷ್ಟು ಬೇಗ ಸಲ್ಲಿಸಿ.\n\n"
        "GSTIN: {supplier_gstin}\n\n"
        "ಕಳುಹಿಸಿದವರು: {firm_name}."
    ),
    "mr": (
        "नमस्कार {supplier_name},\n\n"
        "ही आठवण {firm_name} कडून आमच्या क्लायंटच्या वतीने आहे. "
        "{invoice_date} रोजीचे इनव्हॉइस {invoice_number}, रक्कम "
        "{amount}, सध्याच्या GSTR-2B मध्ये दिसत नाही. जर तुम्ही अद्याप "
        "GSTR-1 दाखल केला नसेल, कृपया लवकर करा जेणेकरून ITC क्लेम "
        "करता येईल.\n\n"
        "GSTIN: {supplier_gstin}\n\n"
        "प्रेषक: {firm_name}."
    ),
}


def render_chase_body(
    ctx: ChaseTemplateContext, *, language: ChaseLanguage
) -> str:
    """Return the chase message body the supplier will read.

    Falls back to English if the language is unknown — we would rather
    ship English than a raw placeholder string to a real supplier.
    """
    tpl = _TEMPLATES.get(language) or _TEMPLATES["en"]
    return tpl.format(
        supplier_name=ctx.supplier_name or "sir/madam",
        firm_name=ctx.firm_name,
        invoice_number=ctx.invoice_number or "—",
        invoice_date=_short_date(ctx.invoice_date_iso) if ctx.invoice_date_iso else "—",
        amount=_rupees(ctx.invoice_amount_paise),
        supplier_gstin=ctx.supplier_gstin,
    )
