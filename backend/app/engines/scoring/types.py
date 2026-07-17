"""Dataclasses for the readiness scoring engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID


@dataclass(frozen=True)
class Blocker:
    """One actionable item on the CA's or client's plate.

    ``paise_impact`` is the money at stake. When it comes from the
    reconciliation summary (supplier_default totals, probable review
    backlog, missing_entry totals) it's the number the command-center
    sorts by. For blockers that don't have a natural paise amount
    (e.g. structural warnings), use 0.
    """
    code: str
    description: str
    owner: str  # 'ca' | 'client'
    paise_impact: int


@dataclass(frozen=True)
class ComponentBreakdown:
    """Per-component score + weight + weighted contribution.

    Persisted verbatim into ``readiness_snapshot.arithmetic`` so the
    dashboard can show 'this is why the score is what it is' with no
    hidden math.
    """
    name: str
    value: float          # 0..100
    weight: float
    weighted: float       # value * weight


@dataclass(frozen=True)
class ScoreInputs:
    """Everything the calculator needs, packaged so it stays pure.

    ``service.py`` builds this by reading the DB (validation flags,
    reconciliation summary, trailing invoice counts, due date from
    rule pack + client scheme). The calculator is a pure function of
    ScoreInputs → ScoreResult.
    """
    # Rule pack.
    rule_pack_version: str
    weights: dict[str, float]                # normalized in the calculator
    days_to_due_date_curve_days: int         # full-score horizon

    # Return context.
    return_type: str                         # 'GSTR1' | 'GSTR3B'
    period: str                              # 'YYYYMM'
    today: date

    # Component inputs.
    invoice_count: int
    validation_error_count: int
    validation_warning_count: int

    # Reconciliation.
    recon_summary: dict[str, Any]            # exactly what ReconResult.summary() returns
    total_register_paise: int

    # Data completeness — trailing month counts, oldest first.
    trailing_month_counts: list[int]
    current_month_count: int

    # Supplier risk.
    risky_supplier_paise: int                # current-period paise from risky suppliers
    total_supplier_paise: int                # current-period total purchase paise

    # Days remaining (positive = future, 0 = today, negative = overdue).
    days_to_due_date: int

    # Paise sums for aggregating validation blockers.
    error_invoice_paise: int
    warning_invoice_paise: int


@dataclass(frozen=True)
class ScoreResult:
    score: int                                # 0..100, integer
    components: tuple[ComponentBreakdown, ...]
    blockers: tuple[Blocker, ...]
    arithmetic: dict[str, Any]
