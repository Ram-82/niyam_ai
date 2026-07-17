"""Canonical invoice shape + content hash.

Every ingester (CSV, Excel, GSTR-2B, future GSP API) converges on
``CanonicalInvoice`` before hitting the DB. Two rules make this the load-
bearing seam:

1. ``content_hash`` is computed HERE, from the normalized tuple. It is the
   unique key for dedup (``invoice_content_hash_uniq`` in the initial
   migration). Any re-ingest of the same logical invoice — even with
   different whitespace, case, or leading-zero variants of the invoice
   number — must produce the same hash. The reconciliation engine
   normalizes with the SAME rules for fuzzy matching (step 5 will import
   ``normalize_invoice_number``).

2. Money is BIGINT paise. Ingesters convert their source units (rupees
   with 2 decimal places) to paise via ``rupees_to_paise`` and never touch
   floats after that.

CanonicalInvoice covers the register side (purchase/sales). GSTR-2B B2B
entries have a similar-but-different shape and use ``CanonicalB2BEntry``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


_INV_SEPARATOR = re.compile(r"[\s\-/\.]+")


def normalize_invoice_number(raw: str) -> str:
    """Uppercase, drop separators, strip leading zeros from each digit run.

    Rules — the goal is that any two humans meaning the same invoice
    produce the same string:

    * ``INV-001``, ``inv 1``, ``INV/0001``, ``INV.001`` all collapse to
      ``INV1`` (letter run + digit run; the digit run's leading zeros go).
    * ``0001`` → ``1`` (single digit run, no letters).
    * ``A0000012345`` → ``A12345`` (letters, then a digit run with lots
      of zero-padding — same rule applies).
    * All-zero runs (``0``, ``000``) collapse to ``0`` so the string is
      never empty.

    Stripping leading zeros of the WHOLE string won't cut it — that leaves
    the zeros between the ``INV`` prefix and the ``1``. So we walk
    letter- and digit-runs and lstrip zeros from each digit-run.
    """
    if raw is None:
        return ""
    s = _INV_SEPARATOR.sub("", str(raw).strip()).upper()
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i].isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append(s[i:j].lstrip("0") or "0")
            i = j
        else:
            j = i
            while j < len(s) and not s[j].isdigit():
                j += 1
            out.append(s[i:j])
            i = j
    return "".join(out) or "0"


def rupees_to_paise(value: Any) -> int:
    """Convert a rupee amount (string, int, float, Decimal) to integer paise.

    Rounds HALF_UP at the paise boundary. Rejects negatives — line-level
    negatives (returns) belong in credit notes, not the invoice register.
    """
    if value is None or value == "":
        return 0
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"invalid amount: {value!r}") from e
    if d < 0:
        raise ValueError(f"negative amount not allowed: {value!r}")
    paise = (d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def paise_display(paise: int) -> str:
    """Format ``paise`` as ``₹1,23,456.78`` (Indian grouping)."""
    rupees = paise / 100
    # Indian digit grouping: last three digits, then pairs.
    s = f"{int(rupees):,}".replace(",", "")
    # Rebuild Indian style manually to avoid locale dep.
    integer_part = str(int(rupees))
    if len(integer_part) > 3:
        head, tail = integer_part[:-3], integer_part[-3:]
        head_groups = []
        while len(head) > 2:
            head_groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            head_groups.insert(0, head)
        grouped = ",".join(head_groups) + "," + tail
    else:
        grouped = integer_part
    frac = paise % 100
    return f"₹{grouped}.{frac:02d}"


# ---------------------------------------------------------------------------
# Canonical invoice dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalInvoice:
    gstin_profile_id: str
    direction: str  # 'purchase' | 'sale'
    invoice_number: str
    invoice_date: date
    counterparty_gstin: Optional[str]
    taxable_value_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    hsn_sac: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """SHA-256 hex of the normalized dedup tuple.

        Fields in the hash — these define what "the same invoice" means for
        dedup:
        * gstin_profile_id (so two firms importing the same supplier
          invoice each keep their own copy)
        * counterparty_gstin (normalized to uppercase, empty string for
          missing — R001 will still flag it separately)
        * normalized invoice number
        * ISO invoice date
        * total_paise (final payable — catches restated amounts)
        """
        parts = (
            str(self.gstin_profile_id),
            (self.counterparty_gstin or "").upper(),
            normalize_invoice_number(self.invoice_number),
            self.invoice_date.isoformat(),
            str(int(self.total_paise)),
        )
        joined = "|".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalB2BEntry:
    """GSTR-2B row after normalization."""
    gstn_pull_id: str
    supplier_gstin: str
    invoice_number: str
    invoice_date: date
    taxable_value_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    cess_paise: int
    itc_available: bool
    note_type: Optional[str] = None  # 'credit_note' | 'debit_note' | None

    @property
    def tax_paise_breakdown(self) -> dict[str, int]:
        return {
            "cgst": self.cgst_paise,
            "sgst": self.sgst_paise,
            "igst": self.igst_paise,
            "cess": self.cess_paise,
        }
