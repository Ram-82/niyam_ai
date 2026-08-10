"""Runs the eight rule functions and returns their flags.

Pipeline is intentionally trivial: iterate a fixed list of rule callables,
call each with (invoice, ctx), collect non-None returns. Rules are
independent — order does not affect outcome.

To add a rule: import it, append to ``RULES``. That's it.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.engines.validation.rules import (
    r001_gstin_missing,
    r002_gstin_checksum,
    r003_date_out_of_period,
    r004_hsn_missing,
    r005_tax_head_mismatch,
    r006_tax_arithmetic,
    r007_duplicate_suspect,
    r008_future_date,
    r009_gstin_state_code,
)
from app.engines.validation.types import Flag, ValidationContext
from app.ingestion.canonical import CanonicalInvoice


RuleFunc = Callable[[CanonicalInvoice, ValidationContext], Optional[Flag]]


RULES: tuple[RuleFunc, ...] = (
    r001_gstin_missing,
    r002_gstin_checksum,
    r003_date_out_of_period,
    r004_hsn_missing,
    r005_tax_head_mismatch,
    r006_tax_arithmetic,
    r007_duplicate_suspect,
    r008_future_date,
    r009_gstin_state_code,
)


def run_pipeline(
    invoice: CanonicalInvoice, ctx: ValidationContext
) -> list[Flag]:
    """Return all flags this invoice trips. Empty list = passes cleanly."""
    return [f for rule in RULES if (f := rule(invoice, ctx)) is not None]


def run_batch(
    invoices: Iterable[CanonicalInvoice], ctx: ValidationContext
) -> dict[str, list[Flag]]:
    """Convenience: map each invoice's content_hash to its flags. Callers
    that persist to ``validation_flag`` want to key by invoice_id — they
    can map content_hash -> invoice_id from their own DB view."""
    return {inv.content_hash(): run_pipeline(inv, ctx) for inv in invoices}
