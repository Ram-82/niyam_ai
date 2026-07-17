"""The v1.0.0 rule pack payload — single source of truth.

Both the seed migration (``alembic/versions/0004_seed_rule_pack.py``) and
the test conftest import ``PAYLOAD`` from here so there is no drift
between "what a fresh deploy seeds" and "what tests assert against."

Adding a new field: bump the version, add a new migration, and update
this module in the same commit as the code that reads the new field.
"""
from __future__ import annotations

from typing import Any


VERSION = "1.0.0"


PAYLOAD: dict[str, Any] = {
    "validation": {
        "r003_period": {"enabled": True},
        "r004_hsn": {
            "default_severity": "warning",
            "default_min_digits": 4,
            "turnover_slabs": [
                {"max_turnover_crores": 5, "severity": "warning", "min_digits": 4},
                {"max_turnover_crores": None, "severity": "error", "min_digits": 6},
            ],
        },
        "r006_tax_arithmetic": {
            "expected_rate_percents": [0, 0.1, 0.25, 3, 5, 12, 18, 28],
            "tolerance_paise": 100,
        },
        "r007_duplicate": {"enabled": True},
    },
    "reconciliation": {
        # Pass 1 exact match: total within ±100 paise (₹1).
        "exact_amount_tolerance_paise": 100,
        # Pass 2 fuzzy gates + scoring.
        "date_window_days": 5,
        "amount_tolerance_percent": 1.0,
        "probable_confidence_threshold": 0.70,
        # Scoring weights (must be non-negative; normalized internally).
        "fuzzy_score_weights": {
            "number_similarity": 0.5,
            "date_closeness": 0.25,
            "amount_closeness": 0.25,
        },
    },
    "scoring": {
        "weights": {
            "validation_pass_rate": 25,
            "reconciliation_match_rate": 40,
            "data_completeness": 15,
            "supplier_risk": 10,
            "days_to_due_date": 10,
        },
        "due_dates": {
            "GSTR1": {"regular": 11, "composition": None},
            "GSTR3B": {"regular": 20, "composition": None},
        },
    },
    "notes": [
        "TODO-VERIFY-WITH-CA: turnover slab thresholds + HSN min-digit counts (R004)",
        "TODO-VERIFY-WITH-CA: tax arithmetic rounding tolerance (R006)",
        "TODO-VERIFY-WITH-CA: fuzzy match date window and amount tolerance (recon Pass 2)",
        "TODO-VERIFY-WITH-CA: probable match confidence threshold",
        "TODO-VERIFY-WITH-CA: scoring weights + days-to-due-date modifier curve",
        "TODO-VERIFY-WITH-CA: due dates for GSTR1/GSTR3B by scheme",
        "TODO-VERIFY-WITH-CA: CDN (credit/debit note) handling — deferred to P2, ITC summaries labeled 'before CDN adjustments'",
    ],
}
