"""Pure scoring math + blocker derivation.

Rules:
* No I/O. No wall-clock. All inputs come in via ``ScoreInputs``.
* Weights are normalized: if the rule pack gives {A: 25, B: 50}, the
  effective weights are {A: 1/3, B: 2/3}. Adding a new component
  never changes existing ones' relative influence beyond dividing
  by the new denominator.
* Blockers pull ``paise_impact`` from the recon summary wherever
  computable. The command center sorts by paise_impact desc, so
  populating a real number matters — every hardcoded 0 is a
  regression in triage quality.
"""
from __future__ import annotations

from typing import Any

from app.engines.scoring.types import (
    Blocker,
    ComponentBreakdown,
    ScoreInputs,
    ScoreResult,
)


ERROR_WEIGHT = 1.0
WARNING_WEIGHT = 0.3

TOP_DEFAULT_SUPPLIER_BLOCKERS = 5


# ---------------------------------------------------------------------------
# Component calculators — each returns a value in [0, 100].
# ---------------------------------------------------------------------------


def _validation_pass_rate(
    invoice_count: int, errors: int, warnings: int
) -> float:
    """Errors weigh more than warnings. Returns 100 when there are no
    invoices (nothing to fail)."""
    if invoice_count <= 0:
        return 100.0
    weighted_failures = errors * ERROR_WEIGHT + warnings * WARNING_WEIGHT
    ratio = max(0.0, invoice_count - weighted_failures) / invoice_count
    return round(_clip(100.0 * ratio), 2)


def _reconciliation_match_rate(matched_paise: int, total_register_paise: int) -> float:
    if total_register_paise <= 0:
        return 100.0
    return round(_clip(100.0 * matched_paise / total_register_paise), 2)


def _data_completeness(current_count: int, trailing_counts: list[int]) -> float:
    if not trailing_counts:
        return 100.0
    avg = sum(trailing_counts) / len(trailing_counts)
    if avg <= 0:
        return 100.0
    return round(_clip(100.0 * current_count / avg), 2)


def _supplier_risk(risky_paise: int, total_paise: int) -> float:
    """100 = no risk (nothing from risky suppliers).
    0 = 100% of purchases from risky suppliers."""
    if total_paise <= 0:
        return 100.0
    fraction_risky = min(1.0, max(0.0, risky_paise / total_paise))
    return round(_clip(100.0 * (1.0 - fraction_risky)), 2)


def _days_to_due_date_score(days_remaining: int, full_score_days: int) -> float:
    """Linear from 100 at ``full_score_days`` down to 0 at day 0.
    Overdue returns 0. ``full_score_days`` <= 0 returns 100 for any
    non-overdue day (guards against division-by-zero on config error)."""
    if days_remaining <= 0:
        return 0.0
    if full_score_days <= 0:
        return 100.0
    return round(_clip(100.0 * days_remaining / full_score_days), 2)


def _clip(x: float) -> float:
    return max(0.0, min(100.0, x))


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def compute_score(inp: ScoreInputs) -> ScoreResult:
    matched_paise = int(inp.recon_summary.get("matched", {}).get("paise", 0))

    raw = {
        "validation_pass_rate": _validation_pass_rate(
            inp.invoice_count,
            inp.validation_error_count,
            inp.validation_warning_count,
        ),
        "reconciliation_match_rate": _reconciliation_match_rate(
            matched_paise, inp.total_register_paise
        ),
        "data_completeness": _data_completeness(
            inp.current_month_count, inp.trailing_month_counts
        ),
        "supplier_risk": _supplier_risk(
            inp.risky_supplier_paise, inp.total_supplier_paise
        ),
        "days_to_due_date": _days_to_due_date_score(
            inp.days_to_due_date, inp.days_to_due_date_curve_days
        ),
    }

    # Normalize weights — a rule pack that omits a component keeps
    # existing components' relative influence.
    weights = {k: float(inp.weights.get(k, 0.0)) for k in raw}
    total_w = sum(weights.values())
    components: list[ComponentBreakdown] = []
    weighted_sum = 0.0
    for name, value in raw.items():
        w = weights[name] / total_w if total_w > 0 else 0.0
        contribution = value * w
        weighted_sum += contribution
        components.append(
            ComponentBreakdown(
                name=name, value=value, weight=weights[name], weighted=round(contribution, 4)
            )
        )

    score = int(round(_clip(weighted_sum)))

    blockers = _derive_blockers(inp)
    arithmetic = {
        "components": [
            {
                "name": c.name,
                "value": c.value,
                "raw_weight": c.weight,
                "normalized_weight": round(
                    c.weight / total_w if total_w > 0 else 0.0, 6
                ),
                "weighted_contribution": c.weighted,
            }
            for c in components
        ],
        "weighted_sum": round(weighted_sum, 4),
        "final_score": score,
        "rule_pack_version": inp.rule_pack_version,
        "period": inp.period,
        "return_type": inp.return_type,
        "computed_for_date": inp.today.isoformat(),
        "days_to_due_date": inp.days_to_due_date,
    }
    return ScoreResult(
        score=score,
        components=tuple(components),
        blockers=blockers,
        arithmetic=arithmetic,
    )


# ---------------------------------------------------------------------------
# Blocker derivation
# ---------------------------------------------------------------------------


def _derive_blockers(inp: ScoreInputs) -> tuple[Blocker, ...]:
    out: list[Blocker] = []
    s = inp.recon_summary

    # Validation errors + warnings (aggregate).
    if inp.validation_error_count > 0:
        out.append(
            Blocker(
                code="VALIDATION_ERRORS",
                description=(
                    f"{inp.validation_error_count} invoice(s) have validation "
                    f"errors — resolve before filing"
                ),
                owner="ca",
                paise_impact=inp.error_invoice_paise,
            )
        )
    if inp.validation_warning_count > 0:
        out.append(
            Blocker(
                code="VALIDATION_WARNINGS",
                description=(
                    f"{inp.validation_warning_count} invoice(s) have "
                    f"validation warnings — review recommended"
                ),
                owner="ca",
                paise_impact=inp.warning_invoice_paise,
            )
        )

    # Reconciliation — pull paise straight from the summary.
    probable = s.get("probable", {})
    if int(probable.get("count", 0)) > 0:
        out.append(
            Blocker(
                code="PROBABLE_PENDING_REVIEW",
                description=(
                    f"{probable['count']} probable match(es) awaiting CA "
                    f"confirm/reject"
                ),
                owner="ca",
                paise_impact=int(probable.get("paise", 0)),
            )
        )

    sup_def = s.get("supplier_default", {})
    if int(sup_def.get("count", 0)) > 0:
        out.append(
            Blocker(
                code="SUPPLIER_DEFAULT_TOTAL",
                description=(
                    f"{sup_def['count']} register invoice(s) have no 2B "
                    f"match — review near-misses before chasing suppliers"
                ),
                owner="ca",
                paise_impact=int(sup_def.get("paise", 0)),
            )
        )
        # Top-N supplier-specific blockers so the command center can
        # spotlight the biggest at-risk suppliers.
        for entry in sup_def.get("top_suppliers", [])[:TOP_DEFAULT_SUPPLIER_BLOCKERS]:
            gstin = entry.get("supplier_gstin", "")
            paise = int(entry.get("paise", 0))
            count = int(entry.get("count", 0))
            out.append(
                Blocker(
                    code=f"TOP_DEFAULT_SUPPLIER_{gstin}",
                    description=(
                        f"supplier {gstin} has {count} unmatched invoice(s) — "
                        f"₹ at risk"
                    ),
                    owner="ca",
                    paise_impact=paise,
                )
            )

    missing = s.get("missing_entry", {})
    if int(missing.get("count", 0)) > 0:
        out.append(
            Blocker(
                code="MISSING_ENTRY_TOTAL",
                description=(
                    f"{missing['count']} 2B entrie(s) not in the purchase "
                    f"register — record before filing"
                ),
                owner="client",
                paise_impact=int(missing.get("paise", 0)),
            )
        )

    # Time pressure — the number matters even when there's no other
    # blocker to attach it to.
    if inp.days_to_due_date <= 3:
        out.append(
            Blocker(
                code="DEADLINE_IMMINENT",
                description=(
                    f"return due in {inp.days_to_due_date} day(s)"
                    if inp.days_to_due_date > 0
                    else f"return is {-inp.days_to_due_date} day(s) overdue"
                ),
                owner="ca",
                paise_impact=0,
            )
        )

    # Rank by paise_impact desc so the dashboard's default order matches
    # what the CA cares about most.
    out.sort(key=lambda b: (-b.paise_impact, b.code))
    return tuple(out)
