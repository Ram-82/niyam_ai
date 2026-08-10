"""The eight P1 validation rules.

Each rule is a pure function ``(invoice, context) -> Optional[Flag]``:

* No I/O. No random. No global state.
* Reads parameters (tolerances, slabs, expected rates) from
  ``context.rule_pack_payload`` — never hardcoded.
* Returns ``None`` on pass, a ``Flag`` on failure.

Adding a new rule R00N:

1. Add a function here matching the pattern.
2. Register it in ``pipeline.py`` (order matters only for readability;
   flags are independent).
3. Add parameters to the active rule_pack payload under ``validation.r00N_*``.
4. Add a test file ``tests/unit/test_rule_r00N.py``.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.engines.validation.gstin import (
    GSTIN_STATE_CODES,
    has_valid_state_code,
    has_valid_structure,
    is_valid_gstin,
    state_code,
)
from app.engines.validation.types import Flag, ValidationContext
from app.ingestion.canonical import CanonicalInvoice, normalize_invoice_number


# ---------------------------------------------------------------------------
# R001 GSTIN_MISSING
# ---------------------------------------------------------------------------


def r001_gstin_missing(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """B2B invoices must carry a counterparty GSTIN.

    We treat every purchase in P1 as B2B (Niyam AI is a CA-facing tool;
    B2C purchase entries are rare in that context and out of scope).
    Sales invoices without a counterparty GSTIN are B2C and pass R001.
    """
    if invoice.direction != "purchase":
        return None
    if invoice.counterparty_gstin:
        return None
    return Flag(
        rule_code="R001",
        severity="error",
        message="counterparty GSTIN is missing on a B2B purchase",
    )


# ---------------------------------------------------------------------------
# R002 GSTIN_CHECKSUM
# ---------------------------------------------------------------------------


def r002_gstin_checksum(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """counterparty_gstin must be a well-formed 15-char GSTIN with a
    valid mod-36 check digit."""
    g = invoice.counterparty_gstin
    if not g:
        return None  # R001 already covers the missing case.
    if not is_valid_gstin(g):
        # Differentiate the failure mode for CAs debugging the flag.
        why = (
            "format" if not has_valid_structure(g) else "check digit"
        )
        return Flag(
            rule_code="R002",
            severity="error",
            message=f"counterparty GSTIN {g!r} fails {why} validation",
        )
    return None


# ---------------------------------------------------------------------------
# R003 DATE_OUT_OF_PERIOD
# ---------------------------------------------------------------------------


def r003_date_out_of_period(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """invoice_date must fall inside ctx.period (YYYYMM)."""
    period = ctx.period
    if not (isinstance(period, str) and len(period) == 6 and period.isdigit()):
        return None  # malformed context — treat as pass so we don't over-flag
    year = int(period[:4])
    month = int(period[4:])
    inv_year, inv_month = invoice.invoice_date.year, invoice.invoice_date.month
    if (inv_year, inv_month) == (year, month):
        return None
    return Flag(
        rule_code="R003",
        severity="warning",
        message=(
            f"invoice date {invoice.invoice_date.isoformat()} is outside "
            f"return period {period}"
        ),
    )


# ---------------------------------------------------------------------------
# R004 HSN_MISSING
# ---------------------------------------------------------------------------


def r004_hsn_missing(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """HSN/SAC on every invoice. Severity + required digits depend on the
    client's turnover slab (rule_pack). Fall back to default when
    turnover is unknown.
    """
    cfg = ctx.validation_config.get("r004_hsn", {})
    default_severity = cfg.get("default_severity", "warning")
    default_min_digits = cfg.get("default_min_digits", 4)
    slabs = cfg.get("turnover_slabs", []) or []

    turnover_paise = ctx.annual_turnover_paise
    slab = _pick_hsn_slab(slabs, turnover_paise)
    severity = slab.get("severity", default_severity) if slab else default_severity
    min_digits = slab.get("min_digits", default_min_digits) if slab else default_min_digits

    hsn = (invoice.hsn_sac or "").strip()
    if not hsn:
        return Flag(
            rule_code="R004",
            severity=severity,
            message=f"HSN/SAC is missing (min digits: {min_digits})",
        )
    # HSN should be digits; trailing letters (SAC has some) are OK for
    # length purposes. Count the digit prefix.
    digits = _leading_digits(hsn)
    if len(digits) < min_digits:
        return Flag(
            rule_code="R004",
            severity=severity,
            message=(
                f"HSN/SAC {hsn!r} is shorter than required ({len(digits)} < "
                f"{min_digits})"
            ),
        )
    return None


def _pick_hsn_slab(slabs: list[dict], turnover_paise: Optional[int]) -> Optional[dict]:
    """Return the first slab whose ``max_turnover_crores`` covers the given
    turnover. ``null`` in ``max_turnover_crores`` is the catch-all bucket.
    Returns ``None`` if turnover is unknown."""
    if turnover_paise is None or not slabs:
        return None
    turnover_crores = turnover_paise / 10_000_000_00  # crores in paise
    for slab in slabs:
        cap = slab.get("max_turnover_crores")
        if cap is None or turnover_crores <= cap:
            return slab
    return slabs[-1]


def _leading_digits(s: str) -> str:
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    return s[:i]


# ---------------------------------------------------------------------------
# R005 TAX_HEAD_MISMATCH
# ---------------------------------------------------------------------------


def r005_tax_head_mismatch(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """Intra-state (same state code) → CGST+SGST only; IGST must be 0.
    Inter-state (different) → IGST only; CGST+SGST must be 0.

    Skips when we can't derive intra vs inter (missing counterparty, or
    counterparty state code invalid) — those cases are R001/R002 territory.
    """
    if not invoice.counterparty_gstin:
        return None
    if not has_valid_structure(invoice.counterparty_gstin):
        return None
    cp_state = state_code(invoice.counterparty_gstin)
    intra_state = cp_state == ctx.client_state_code

    if intra_state:
        if invoice.igst_paise > 0:
            return Flag(
                rule_code="R005",
                severity="error",
                message=(
                    f"intra-state supply (state {ctx.client_state_code}) "
                    f"has IGST > 0 — expected CGST+SGST split"
                ),
            )
    else:
        if invoice.cgst_paise > 0 or invoice.sgst_paise > 0:
            return Flag(
                rule_code="R005",
                severity="error",
                message=(
                    f"inter-state supply ({ctx.client_state_code} <-> "
                    f"{cp_state}) has CGST/SGST > 0 — expected IGST only"
                ),
            )
    return None


# ---------------------------------------------------------------------------
# R006 TAX_ARITHMETIC
# ---------------------------------------------------------------------------


def r006_tax_arithmetic(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """Actual tax must equal ``taxable × rate/100`` within tolerance
    for at least one of the ``expected_rate_percents`` in the rule pack.

    We don't know the invoice's declared rate (P1 CSV has no rate column),
    so we try each expected rate and pass if any matches. This flags
    both "arithmetic wrong for a valid rate" and "tax computed at a
    non-standard rate" — both are things a CA wants to see.

    ``0`` and near-zero rates (e.g. 0.1, 0.25) are legitimate for certain
    HSNs; keeping them in the rate list means those invoices don't
    false-flag.
    """
    cfg = ctx.validation_config.get("r006_tax_arithmetic", {})
    tolerance_paise = int(cfg.get("tolerance_paise", 100))
    rates = cfg.get("expected_rate_percents") or [0, 5, 12, 18, 28]

    actual = invoice.cgst_paise + invoice.sgst_paise + invoice.igst_paise
    if invoice.taxable_value_paise == 0 and actual == 0:
        return None  # zero-value line — vacuously fine

    for rate in rates:
        expected = round(invoice.taxable_value_paise * float(rate) / 100.0)
        if abs(expected - actual) <= tolerance_paise:
            return None
    return Flag(
        rule_code="R006",
        severity="error",
        message=(
            f"tax total {actual} paise does not match any expected rate "
            f"{rates} on taxable {invoice.taxable_value_paise} paise "
            f"(tolerance ±{tolerance_paise} paise)"
        ),
    )


# ---------------------------------------------------------------------------
# R007 DUPLICATE_SUSPECT
# ---------------------------------------------------------------------------


def r007_duplicate_suspect(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """Two invoices sharing (counterparty_gstin, normalized_invoice_number)
    in the same period are duplicate suspects.

    Identical content_hash is already blocked by the DB unique index on
    (gstin_profile_id, content_hash) — so this rule catches the more
    interesting case: same logical invoice but different amounts / dates.

    Requires ``ctx.duplicate_key_counts`` to be precomputed by the caller.
    """
    if not ctx.validation_config.get("r007_duplicate", {}).get("enabled", True):
        return None
    if not invoice.counterparty_gstin:
        return None
    key = (
        invoice.counterparty_gstin.upper(),
        normalize_invoice_number(invoice.invoice_number),
    )
    count = ctx.duplicate_key_counts.get(key, 0)
    if count <= 1:
        return None
    return Flag(
        rule_code="R007",
        severity="warning",
        message=(
            f"{count} invoices share counterparty GSTIN "
            f"{invoice.counterparty_gstin} + invoice number "
            f"{invoice.invoice_number!r} in this period"
        ),
    )


# ---------------------------------------------------------------------------
# R008 FUTURE_DATE
# ---------------------------------------------------------------------------


def r008_future_date(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    if invoice.invoice_date > ctx.today:
        return Flag(
            rule_code="R008",
            severity="error",
            message=(
                f"invoice date {invoice.invoice_date.isoformat()} is in the "
                f"future (today: {ctx.today.isoformat()})"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# R009 GSTIN_STATE_CODE
# ---------------------------------------------------------------------------


def r009_gstin_state_code(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> Optional[Flag]:
    """counterparty_gstin first two chars must be a recognised GSTN state/UT
    code. R001 covers missing GSTINs; R002 covers structural failures — so
    this rule only runs when the GSTIN passes structure validation.
    """
    g = invoice.counterparty_gstin
    if not g:
        return None  # R001 handles missing
    if not has_valid_structure(g):
        return None  # R002 handles structural failure
    if not has_valid_state_code(g):
        return Flag(
            rule_code="R009",
            severity="error",
            message=(
                f"counterparty GSTIN {g!r} has unrecognised state code "
                f"{g[:2]!r} — not in the GSTN state/UT master "
                f"({len(GSTIN_STATE_CODES)} statutory codes)"
            ),
        )
    return None
