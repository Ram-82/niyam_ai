"""Authoritative allowlist for the legal-acceptance gate.

Every mutating route (POST/PUT/PATCH/DELETE) in the API MUST appear in
exactly one of ``INGRESS_ROUTES`` or ``NON_INGRESS_ROUTES``. The meta-test
in ``tests/integration/test_gate_coverage.py`` introspects
``app.routes`` and fails CI when:

  * A new mutating route is not classified in either set (forces a
    reviewer to look at each new endpoint and consciously decide).
  * A route in ``INGRESS_ROUTES`` does not actually depend on
    ``require_legal_accepted`` (catches wire-up regressions).

**"Data ingress"** means: introduces new records containing personal
data about a third party — a CA-firm client, a client contact, a
supplier, or transaction rows about them. Data-subject inventory is
in ``docs/compliance/retention-and-erasure.md`` § 2.

If a document hash changes, acceptance is pending again and every
ingress route is blocked during that window (the point of the gate).
Non-ingress routes stay open during re-acceptance so a firm can
still service existing data.
"""
from __future__ import annotations

from typing import FrozenSet, Tuple


Route = Tuple[str, str]  # (method, path)


# ---------------------------------------------------------------------------
# INGRESS — must be gated by require_legal_accepted.
# ---------------------------------------------------------------------------
INGRESS_ROUTES: FrozenSet[Route] = frozenset({
    ("POST", "/clients"),                                         # new client row
    ("POST", "/clients/{client_id}/gstins"),                      # new gstin_profile
    ("POST", "/clients/import"),                                  # bulk client CSV
    ("POST", "/imports/invoices"),                                # invoice upload
    ("POST", "/imports/gstr2b"),                                  # 2B upload
    ("POST", "/supplier-contacts"),                               # new supplier_contact
    ("POST", "/ocr/invoice"),                                     # new ocr_extraction w/ invoice text
    ("POST", "/ocr/extractions/{extraction_id}/accept"),          # materialises invoice row
    ("POST", "/gsp/pull"),                                        # pulls gstn_pull + b2b_entry from GSTN
    ("POST", "/whatsapp/delivery-requests"),                      # captures client contact snapshot
    ("POST", "/whatsapp/delivery-requests/chase"),                # same
})


# ---------------------------------------------------------------------------
# NON_INGRESS — MUST NOT be gated. Each entry is an explicit reviewer
# statement that this route does not introduce new third-party personal
# data. Adding a route here requires seeing this file in review.
# ---------------------------------------------------------------------------
NON_INGRESS_ROUTES: FrozenSet[Route] = frozenset({
    # --- auth flow: no tenant data written -------------------------------
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/password/change"),
    ("POST", "/auth/password/forgot"),
    ("POST", "/auth/password/reset"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/register"),
    ("POST", "/auth/totp/setup"),
    ("POST", "/auth/totp/verify"),

    # --- legal itself: chicken-and-egg. accepting the gate cannot be gated
    #     by the gate.
    ("POST", "/legal/accept"),

    # --- CA-firm staff / assignments: firm's OWN data, not third-party ---
    ("POST", "/assignments"),
    ("DELETE", "/assignments/{user_id}/{client_id}"),
    ("POST", "/invites/"),
    ("DELETE", "/invites/{invite_id}"),
    ("POST", "/invites/{invite_id}/resend"),
    ("PATCH", "/firm/settings"),

    # --- GSP session lifecycle: no rows carrying personal data ----------
    ("POST", "/gsp/consent"),
    ("POST", "/gsp/consent/confirm"),
    ("POST", "/gsp/disconnect"),

    # --- system schedulers (system actor, no user-driven ingress) -------
    ("POST", "/gsp/scheduler/run"),
    ("POST", "/scheduler/reminders/sweep"),

    # --- state transitions on existing rows -----------------------------
    ("POST", "/filings/generate"),
    ("POST", "/filings/{filing_id}/approve"),
    ("POST", "/filings/{filing_id}/mark-filed"),
    ("POST", "/filings/{filing_id}/unlock"),
    ("POST", "/flags/{flag_id}/resolve"),
    ("POST", "/match-results/{match_id}/confirm"),
    ("POST", "/match-results/{match_id}/mark-near-miss-reviewed"),
    ("POST", "/match-results/{match_id}/mark-reviewed"),
    ("POST", "/match-results/{match_id}/reject"),
    ("POST", "/ocr/extractions/{extraction_id}/reject"),
    ("POST", "/whatsapp/delivery-requests/{delivery_request_id}/approve"),
    ("POST", "/whatsapp/delivery-requests/{delivery_request_id}/send"),

    # --- computations over existing data (no new records w/ PII) --------
    ("POST", "/engines/reconcile"),
    ("POST", "/engines/score"),
    ("POST", "/engines/validate"),
    ("POST", "/narrator/preview"),

    # --- config / metadata: rule pack management ------------------------
    ("POST", "/rule-packs/clone"),
    ("POST", "/rule-packs/{pack_id}/activate"),
    ("PATCH", "/rule-packs/{pack_id}"),

    # --- edits/deletes of existing rows (no new ingress) ----------------
    ("PATCH", "/clients/{client_id}"),
    ("PATCH", "/supplier-contacts/{contact_id}"),
    ("DELETE", "/supplier-contacts/{contact_id}"),

    # --- external inbound webhook (delivery status callback from Meta) --
    ("POST", "/whatsapp/webhook"),
})
