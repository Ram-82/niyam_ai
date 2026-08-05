"""WeasyPrint wrapper — HTML + CSS → PDF bytes.

Split from :mod:`app.pdf.service` so the template-loading + rendering
mechanics are separately testable from the DB-side facts assembly.

WeasyPrint requires cairo + pango + gdk-pixbuf on the host. The
backend Dockerfile installs them via apt. In a P3 deploy that will
still be true — WeasyPrint is the pick over pure-Python alternatives
(xhtml2pdf, fpdf2) because we need real Unicode + Devanagari/Kannada
shaping, and cairo/pango is the reference stack for that.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import jinja2


log = logging.getLogger("niyam.pdf.renderer")


_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


_env: Optional[jinja2.Environment] = None


def _get_env() -> jinja2.Environment:
    """Lazy-init the Jinja environment. Autoescape ON — the templates
    interpolate user-provided strings (client_name, prose blocks)."""
    global _env
    if _env is None:
        _env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html", "htm"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        _env.filters["rupees"] = _rupees_filter
        _env.filters["percent"] = _percent_filter
    return _env


def _rupees_filter(paise: int) -> str:
    """Format a paise int as ₹N,NN,NNN. Whole rupees, Indian grouping.

    Kept identical to app.narrator.mock_adapter._rupees so numbers on
    the PDF match numbers the CA saw on the preview screen.
    """
    if paise is None:
        return "—"
    try:
        p = int(paise)
    except (TypeError, ValueError):
        return str(paise)
    negative = p < 0
    p = abs(p)
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


def _percent_filter(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value)}%"
    except (TypeError, ValueError):
        return str(value)


def render_html_to_pdf(html: str, *, base_url: Optional[str] = None) -> bytes:
    """Render an HTML string to PDF bytes.

    ``base_url`` lets WeasyPrint resolve <link>/<img> href relative paths.
    Defaults to the pdf module's static directory so ``<link rel="stylesheet"
    href="two_pager.css">`` in the template picks up the shipped CSS.
    """
    try:
        from weasyprint import HTML  # local import so DB-only paths never touch cairo
    except ImportError as e:
        raise RuntimeError(
            "weasyprint not installed. Add to pyproject and rebuild the "
            "image (needs libcairo2 + libpango-1.0-0 apt packages)."
        ) from e

    return HTML(string=html, base_url=base_url or str(_STATIC_DIR)).write_pdf()


def render_template_to_pdf(template_name: str, context: dict) -> bytes:
    """Load a template, render with ``context``, hand to WeasyPrint.

    ``context`` MUST NOT contain any float-typed money — every rupee
    number should be either a paise int (rendered via the ``rupees``
    filter in-template) or a pre-formatted string. This keeps the
    "engines own the numbers" invariant intact.
    """
    tpl = _get_env().get_template(template_name)
    html = tpl.render(**context)
    return render_html_to_pdf(html, base_url=str(_STATIC_DIR))
