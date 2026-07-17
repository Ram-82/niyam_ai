"""GSP (GST Suvidha Provider) API interface — P2.

**Intended contract.** In P2, ``pull_gstr2b(gstin, period)`` initiates a
consented GSTN pull via a licensed GSP intermediary and returns the raw
GSTR-2B JSON exactly as the GSTN would emit it. The consent handshake
(OTP against the GSTIN's registered mobile) is scoped by ``client_id``
and logged to ``consent_log`` before the first pull; subsequent pulls
reuse the session token until it expires. Every pull writes a
``gstn_pull`` row with ``source='gsp_api'`` (P1 imports write
``'json_import'``), so the reconciliation engine picks it up with no
change to the downstream code. Rate-limits and per-call cost accounting
are the GSP layer's responsibility.

**Why stubbed in P1.** GSP access is a licensed, paid integration
requiring a signed ASP+GSP contract, sandbox credentials, and an
approved production nomination on each client's GSTN account. None of
that is meaningful without a real GSTN engagement. P1 accepts 2B via
JSON upload (see ``app/api/imports.py``) which uses the SAME
``gstn_pull`` row shape, so the demo, tests, and downstream engines
already exercise the "post-pull" flow end-to-end.

Also expected in the P2 implementation:

* ``check_gstin_status(gstin) -> {active, cancelled, provisionally_cancelled}``
  — powers the "inactive supplier" validation rule (R009) that the
  master prompt (§5) shows in the red-flag flowchart. P1 uses R002
  (checksum failure) as a demo stand-in for this alert.
* ``fetch_filing_status(gstin, period, return_type)`` — informs the
  supplier_risk component of readiness scoring beyond the current
  in-period ``supplier_default`` bucket.
"""
from __future__ import annotations


class GSPUnavailable(RuntimeError):
    """Raised by every stubbed call so P1 code paths never silently
    succeed against fake data."""


def pull_gstr2b(gstin: str, period: str) -> None:
    raise GSPUnavailable(
        "GSP pull is stubbed in P1. Upload 2B JSON via POST /imports/gstr2b."
    )


def check_gstin_status(gstin: str) -> None:
    raise GSPUnavailable(
        "GSTN status check is stubbed in P1. Register R002 (checksum) is the "
        "current stand-in flag."
    )


def fetch_filing_status(gstin: str, period: str, return_type: str) -> None:
    raise GSPUnavailable(
        "GSTN filing-status check is stubbed in P1."
    )
