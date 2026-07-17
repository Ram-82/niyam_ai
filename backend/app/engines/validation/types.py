"""Dataclasses shared by the validation pipeline.

``Flag`` is what a rule function returns (or ``None`` if the rule passes).
``ValidationContext`` bundles everything a rule might need beyond the
invoice itself — the active rule pack, the return period, the client's
state code (for R005 tax-head derivation), and pre-computed structures
like duplicate-key counts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass(frozen=True)
class Flag:
    rule_code: str            # 'R001'..'R008'
    severity: str             # 'error' | 'warning'
    message: str              # human-readable one-liner


@dataclass(frozen=True)
class ValidationContext:
    rule_pack_version: str
    rule_pack_payload: dict[str, Any]

    # Return period being prepared, e.g. '202606'. Used by R003.
    period: str

    # Today's date in the Asia/Kolkata display TZ (comes in from caller).
    # Used by R008.
    today: date

    # First 2 digits of the client's OWN GSTIN — used by R005 to derive
    # intra-state vs inter-state supply from counterparty_gstin.
    client_state_code: str

    # Optional client turnover in paise. Feeds R004's slab picker. If
    # None, R004 falls back to default_severity / default_min_digits.
    annual_turnover_paise: Optional[int] = None

    # For R007: count of invoices in the current batch (+ already in DB
    # for the same period) keyed by (counterparty_gstin, normalized_number).
    # If a key's count > 1, both rows are duplicate suspects.
    duplicate_key_counts: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def validation_config(self) -> dict[str, Any]:
        return self.rule_pack_payload.get("validation", {})
